from PIL import Image

from app.services import image_service


def test_dominant_color_is_the_average_color_of_the_cover(app):
    covers = image_service._covers_dir()
    covers.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (20, 30), (200, 40, 40)).save(covers / "red.jpg", "JPEG", quality=100)

    color = image_service.dominant_color("red.jpg")

    r, g, b = (int(color[i:i + 2], 16) for i in (1, 3, 5))
    assert r > 180 and g < 70 and b < 70  # JPEG compression nudges the values slightly


def test_dominant_color_is_none_for_a_missing_file(app):
    assert image_service.dominant_color("does-not-exist.jpg") is None
