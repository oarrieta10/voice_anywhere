from PIL import Image

from voice_anywhere.overlay import to_windows_pixels


def test_pixels_are_premultiplied_and_in_blue_green_red_alpha_order():
    img = Image.new("RGBA", (2, 1))
    img.putpixel((0, 0), (200, 100, 50, 255))  # opaque: colours unchanged
    img.putpixel((1, 0), (255, 255, 255, 128))  # half see-through white
    data = to_windows_pixels(img)
    assert data[:4] == bytes([50, 100, 200, 255])
    assert data[4:] == bytes([128, 128, 128, 128])
