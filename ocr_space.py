import argparse
from datetime import datetime
from json import loads as jlds
import io
import re
import logging
from receipt_scanner.api import api_scan


class ReceiptSummary:
    TOTAL_GUESS_NOT_AVALABLE_STRING = "n.a."
    total_guess_patterns = [
        re.compile(r'TOTALE COMPLESSIVO', re.IGNORECASE),
        re.compile(r'^TOTALE', re.IGNORECASE),
        re.compile(r'IMPORTO PAGATO', re.IGNORECASE),
        re.compile(r'SUBTOTALE', re.IGNORECASE),
    ]
    date_pattern = re.compile(r'(?P<day>\d+)[-/](?P<month>\d+)[-/](?P<year>\d+)\s+(?P<hour>\d+)[:\.](?P<minute>\d+)(?:[:\.](?P<second>\d+))?')

    def __init__(self):
        self.items = []
        self._ocrspace_results: OCRSpaceResult = None
        self._cached_total_guess = None

    def __str__(self):
        datestr = self.date.strftime("%x %X")
        return f"{self.vendor}, on {datestr} - Total: {self.total_guess()}"

    @staticmethod
    def fromOCRSpaceJsonResponse(jres: str):
        summary = ReceiptSummary()
        raw_json = jlds(jres)
        summary.ocrspace_results = OCRSpaceResult.from_dict(raw_json)
        return summary

    @property
    def ocrspace_results(self) -> OCRSpaceResult:
        return self._ocrspace_results

    @ocrspace_results.setter
    def ocrspace_results(self, results):
        self._cached_total_guess = None
        self._ocrspace_results = results

    @property
    def vendor(self) -> str:
        parsed_text_lines = self.parsed_text_lines()
        vendor = None
        if parsed_text_lines:
            vendor = re.sub(r'[^\w\s]', "", parsed_text_lines[0]).strip() # dumb guess
        return vendor or ReceiptSummary.TOTAL_GUESS_NOT_AVALABLE_STRING

    @property
    def date(self) -> datetime:
        parsed_text_lines = self.parsed_text_lines()
        date_guess = None
        if parsed_text_lines:
            for line in parsed_text_lines:
                date_match = ReceiptSummary.date_pattern.search(line)
                if date_match:
                    year = int(date_match.group("year"))
                    month = int(date_match.group("month"))
                    day = int(date_match.group("day"))
                    hour = int(date_match.group("hour"))
                    minute = int(date_match.group("minute"))
                    second = int(date_match.group("second") or "00")
                    return datetime(year=year, month=month, day=day, hour=hour, minute=minute, second=second)
        return datetime.now()
        
    def total_guess(self) -> float:
        parsed_text_lines = self.parsed_text_lines()
        if self._cached_total_guess:
            return self._cached_total_guess
        total_guess = None
        if parsed_text_lines:
            for pattern in ReceiptSummary.total_guess_patterns:
                for line in parsed_text_lines:
                    match = pattern.search(line.strip())
                    if match:
                        # DEBUG
                        logging.debug(f"Total match found at line[{line}] regex[{str(pattern)}]")
                        total_line_columns = line.strip().split("\t")
                        if len(total_line_columns) > 1:
                            guess_match = re.search(r'(\d+[\.,]\d{2,2})', total_line_columns[-1])
                            if guess_match:
                                try:
                                    guess_value = guess_match.group(1).replace(",", ".")
                                    total_guess = float(guess_value)
                                    break
                                except ValueError:
                                    logging.debug(f"{guess_value} cannot be cast to float - line[{line}]")
                                    pass
                        else:
                            logging.debug(f"No numeric value at line[{line}]")
                if total_guess:
                    break
        return total_guess or "n.a."  
        
    def parsed_text_lines(self) -> list[str] | None:
        if self.ocrspace_results:
            result = self.ocrspace_results.parsed_results[0]
            parsed_text_lines = result.parsed_text.splitlines()
            return parsed_text_lines
        return None


class OCRSpaceWord:
    word_text: str
    left: int
    top: int
    height: int
    width: int

    @staticmethod
    def from_dict(dictobj: dict):
        ret = OCRSpaceWord()
        ret.word_text = dictobj.get("WordText")
        ret.left = int(dictobj.get("Left"))
        ret.top = int(dictobj.get("Top"))
        ret.height = int(dictobj.get("Height"))
        ret.width = int(dictobj.get("Width"))
        return ret

    @property
    def bottom(self):
        return self.top + self.height

    @property
    def right(self):
        return self.left + self.width


class OCRSpaceLine:
    line_text: str
    words: list[OCRSpaceWord]
    max_height: int
    min_top: int

    def __init__(self):
        pass

    def __str__(self):
        return self.line_text

    @staticmethod
    def from_dict(dictobj: dict):
        ret = OCRSpaceLine()
        ret.line_text = dictobj.get("LineText")
        ret.words = [OCRSpaceWord.from_dict(worddict) for worddict in dictobj.get("Words", [])]
        ret.max_height = int(dictobj.get("MaxHeight"))
        ret.min_top = int(dictobj.get("MinTop"))
        return ret

    def is_same_line(self, other):
        selfhigh = self.upper_bound
        selfbottom = self.lower_bound
        otherhigh = other.upper_bound
        otherbottom = other.lower_bound
        return selfhigh <= otherbottom and otherhigh <= selfbottom

    @property
    def left_bound(self):
        allefts = [w.left for w in self.words]
        if len(allefts) > 0:
            return min(allefts)
        return -1
    @property
    def right_bound(self):
        allrights = [w.right for w in self.words]
        if len(allrights) > 0:
            return max(allrights)
        return -1
    @property
    def lower_bound(self):
        alllows = [w.bottom for w in self.words]
        if len(alllows) > 0:
            return max(alllows)
    @property
    def upper_bound(self):
        allups = [w.top for w in self.words]
        if len(allups) > 0:
            return min(allups)


class OCRSpaceOverlay:
    lines: list[OCRSpaceLine]
    @staticmethod
    def from_dict(dictobj: dict):
        ret = OCRSpaceOverlay()
        ret.lines = [OCRSpaceLine.from_dict(linedict) for linedict in dictobj.get("Lines", [])]
        return ret

    def lines_sorted_by_upperbound(self) -> list[OCRSpaceLine]:
        return sorted(self.lines, key=lambda line: line.upper_bound, reverse=False)

class OCRSpaceParsedResult(object):
    overlay: OCRSpaceOverlay
    file_parse_exit_code: int
    text_orientation: str
    parsed_text: str
    error_message: str
    error_details: str
    @staticmethod
    def from_dict(dictobj: dict):
        ret = OCRSpaceParsedResult()
        overlay_obj = dictobj.get("Overlay") or dictobj.get("TextOverlay", None)        
        ret.overlay = OCRSpaceOverlay.from_dict(overlay_obj)
        ret.file_parse_exit_code = int(dictobj.get("FileParseExitCode"))
        ret.text_orientation = dictobj.get("TextOrientation")
        ret.parsed_text = dictobj.get("ParsedText")
        ret.error_message = dictobj.get("ErrorMessage")
        ret.error_details = dictobj.get("ErrorDetails")
        return ret
    
    def tableize(self):
        table = []
        sorted = self.overlay.lines_sorted_by_upperbound()
        #debug 
        print("Raw lines sorted:")
        print("\n".join([str(line) for line in sorted]))
        print("")
        for gIdx, line in enumerate(sorted):
            if gIdx == 0:
                table.append([line])
            else:
                previous_line = table[-1][0]
                if previous_line.is_same_line(line):
                    table[-1].append(line)
                else: # end of table line
                    table[-1].sort(key=lambda col: col.left_bound)
                    # debug
                    print("|".join([str(col) for col in table[-1]]))

                    table.append([line])
        return table

class OCRSpaceResult:
    parsed_results: list[OCRSpaceParsedResult]
    ocr_exit_code: int
    is_errored_on_processing: bool
    processing_time_in_milliseconds: float
    searchable_pdf_url: str

    @staticmethod
    def from_dict(dictobj: dict):
        ret = OCRSpaceResult
        ret.parsed_results = [OCRSpaceParsedResult.from_dict(res) for res in dictobj.get("ParsedResults")]
        ret.ocr_exit_code = int(dictobj.get("OCRExitCode"))
        ret.is_errored_on_processing = bool(dictobj.get("IsErroredOnProcessing"))
        ret.processing_time_in_milliseconds = float(dictobj.get("ProcessingTimeInMilliseconds"))
        ret.searchable_pdf_url = dictobj.get("SearchablePDFURL")
        return ret

def parse_ocrspace_json_text(result_json: str):
    raw_result = jlds(result_json)
    result = OCRSpaceResult.from_dict(raw_result)
    result.parsed_results[0].tableize()
    

def quick_total_from_parsed_text(result_json: str):
    raw_result = jlds(result_json)
    result = OCRSpaceResult.from_dict(raw_result)
    total_regex = re.compile(r'^.*totale complessivo', re.IGNORECASE)
    for linenum, line in enumerate(result.parsed_results[0].parsed_text.split("\n")):
        match = total_regex.match(line)
        if match:
            #debug
            # print(f"Line #{linenum} matches 'TOTALE COMPLESSIVO': {line}")
            columns = [col for col in line.split("\t") if len(col.strip())>0] # filter out empty columns
            total = columns[-1]
            return total
    return None            


def deserialiser(arguments):
    with io.open(arguments.RESFILE, 'rt') as ifile:
        restext = ifile.read()
        if arguments.quick:
            total = quick_total_from_parsed_text(restext)
            print(total if total else "Total non found")
        else:
            parse_ocrspace_json_text(restext)
            
if __name__ == "__main__":

    logging.basicConfig(level=logging.DEBUG)

    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers()

    api_parser = subparsers.add_parser("api", help="Send image to OCRSpace API and get ocr-ed response")
    api_parser.add_argument("IMAGE")
    api_parser.set_defaults(which="api")

    deserialiser_parser = subparsers.add_parser("parse", help="Analyse OCRSpace API response (json) and extract data")
    deserialiser_parser.add_argument("RESFILE")
    deserialiser_parser.add_argument("--quick", action="store_true")
    deserialiser_parser.set_defaults(which="deserialise")

    arguments = parser.parse_args()
    if arguments.which == "api":
        # TODO: handle result
        restext = api_scan(arguments.IMAGE)
        summary = ReceiptSummary.fromOCRSpaceJsonResponse(restext)
        print(str(summary))
        
    elif arguments.which == "deserialise":
        # TODO: handle result
        deserialiser(arguments)
    else:
        logging.debug("Unknown command")
    
    