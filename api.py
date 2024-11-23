import requests
from os import getenv
from base64 import b64encode
from receipt_scanner.image_resizer import resize_image_to_max_size
from os.path import dirname, basename, join as pjoin
from os import remove
import io
from tempfile import TemporaryFile


def ocr_space_api_file(filename, overlay=False, api_key='helloworld', language='eng') -> str:
    """ OCR.space API request with local file.
        Python3.5 - not tested on 2.7
    :param filename: Your file path & name.
    :param overlay: Is OCR.space overlay required in your response.
                    Defaults to False.
    :param api_key: OCR.space API key.
                    Defaults to 'helloworld'.
    :param language: Language code to be used in OCR.
                    List of available language codes can be found on https://ocr.space/OCRAPI
                    Defaults to 'en'.
    :return: Result in JSON format.
    """

    payload = {'isOverlayRequired': overlay,
               'apikey': api_key,
               'language': language,
               'isTable': True,
               'OCREngine': 2,
               }
    with open(filename, 'rb') as f:
        r = requests.post('https://api.ocr.space/parse/image',
                          files={filename: f},
                          data=payload,
                          )
    return r.content.decode()


def ocr_space_api_buffer(buffer_bytes, overlay=False, api_key='helloworld', language='eng') -> str:
    """ OCR.space API request with local file.
        Python3.5 - not tested on 2.7
    :param filename: Your file path & name.
    :param overlay: Is OCR.space overlay required in your response.
                    Defaults to False.
    :param api_key: OCR.space API key.
                    Defaults to 'helloworld'.
    :param language: Language code to be used in OCR.
                    List of available language codes can be found on https://ocr.space/OCRAPI
                    Defaults to 'en'.
    :return: Result in JSON format.
    """

    image_text =  b64encode(buffer_bytes).decode()
    payload = {'isOverlayRequired': overlay,
               'apikey': api_key,
               'language': language,
               'isTable': True,
               'OCREngine': 2,
               'base64Image': f"data:image/jpg;base64,{image_text}"
               }
    r = requests.post('https://api.ocr.space/parse/image',
                          data=payload,
                          )
    return r.content.decode()


def api_scan(input_image: str|io.BytesIO):
    # fetch API key
    key = getenv("OCR_SPACE_KEY")
    if not key:
        raise Exception("OCR Space API key missing ('OCR_SPACE_KEY' env var expected)")
    # resize image
    resized_image_bytes, quality = resize_image_to_max_size(input_image, 1024*1024)
    # outname = f"tmp_{basename(input_image)}"
    # output_image = pjoin(dirname(input_image), outname)
    # with io.open(output_image, "wb") as tmpfile:
    #     tmpfile.write(resized_image_bytes)
    restext = ocr_space_api_buffer(resized_image_bytes, api_key=key)
    # debug
    # print(restext)
    # remove(output_image)

    # print(quick_total_from_parsed_text(restext))
    return restext