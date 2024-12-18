from PIL import Image
import io

def resize_image_to_max_size(image_ref, max_size_bytes, convert_grayscale=True):
    """
    Resize an image to fit within a given maximum size in bytes.
    
    Args:
        image_ref (string path to image file or IO[Bytes] image buffer): Path to the input image.
        max_size_bytes (int): Maximum size of the output image in bytes.
        convert_grayscale (bool): Whether to convert the image to grayscale for size reduction.
        
    Returns:
        bytes: The resized image in bytes format or None if the operation fails.
    """
    # Open the image
    with Image.open(image_ref) as img:
        
        # Convert to grayscale if the flag is set
        if convert_grayscale:
            img = img.convert("L")  # 'L' mode is for grayscale
        
        # Take input PIL Image and returns the same image saved with given quality 
        def apply_image_quality(image, quality):
            with io.BytesIO() as buffer:
                image.save(buffer, format="JPEG", quality=quality)
                return buffer.getvalue()
        
        # Initial quality setting for the image
        quality = 95
        
        # Get the initial size of the image
        image_bytes = apply_image_quality(img, quality)
        
        # If the image is already smaller than the target size, return as is
        if len(image_bytes) <= max_size_bytes:
            return (image_bytes, quality)
        
        # Reduce quality until the image is within the desired size
        while len(image_bytes) > max_size_bytes and quality > 10:
            quality -= 5  # Reduce quality by 5 each iteration
            image_bytes = apply_image_quality(img, quality)
        
        # Check if the final size is acceptable
        if len(image_bytes) <= max_size_bytes:
            return (image_bytes, quality)
        else:
            return (None, None) # Could not reduce size to desired max
        
# Example usage:
# image_bytes = resize_image_to_max_size("path_to_image.jpg", 100000)  # Limit to 100 KB
# if image_bytes:
#     with open("resized_image.jpg", "wb") as f:
#         f.write(image_bytes)
