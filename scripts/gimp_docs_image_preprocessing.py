"""A script for preprocessing screenshots to be used in documentation.

The script crops the image by 1 on each side and fills in the corners so they are not
round.
This removes any visible background and makes the images usable both in light and dark
mode without any artifacts around the edges.

This script is mostly useful when preprocessing screenshots taken of the application
window created through WSL and might not be relevant for other platforms.
"""


def fill_in_corner(image, x0, y0, x_direction, y_direction) -> None:
    color = image.pick_color(
        image.get_layers(), x0 + 5 * x_direction, y0 + 5 * y_direction, True, True, 1
    )[1]
    Gimp.context_set_foreground(color)
    Gimp.pencil(
        image.get_layers()[0],
        [x0, y0 + 6 * y_direction, x0, y0, x0 + 6 * x_direction, y0],
    )
    Gimp.pencil(
        image.get_layers()[0],
        [
            x0 + 1 * x_direction,
            y0 + 3 * y_direction,
            x0 + 1 * x_direction,
            y0 + 1 * y_direction,
            x0 + 3 * x_direction,
            y0 + 1 * y_direction,
        ],
    )


# Retrieve the active image
image = Gimp.get_images()[0]

# Crop 1 along each edge
image.crop(image.get_width() - 2, image.get_height() - 2, 1, 1)

# Reduce brush size to paint only pencil path provided
Gimp.context_set_brush_size(1)
# Top-left
fill_in_corner(image, 0, 0, 1, 1)
# Top-right
fill_in_corner(image, image.get_width() - 1, 0, -1, 1)
# Bottom-right
fill_in_corner(image, image.get_width() - 1, image.get_height() - 1, -1, -1)
# Bottom-left
fill_in_corner(image, 0, image.get_height() - 1, 1, -1)
