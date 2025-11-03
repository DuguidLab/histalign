# histalign

[![PyPI - Version](https://img.shields.io/pypi/v/histalign.svg)](https://pypi.org/project/histalign)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/histalign.svg)](https://pypi.org/project/histalign)

-----

## Table of Contents

- [Installation](#installation)
- [Known Issues](#known-issues)
- [License](#license)

## Installation

```console
pip install histalign
```

## Known Issues

### Seemingly grayscale images are not recognised

When opening an image directory for alignment, it can appear as though the application cannot recognise any of the images present even though you think they are grayscale. That is most likely due to the way the images were exported when acquired.

A simple way to check whether they are truly grayscale or RGB in disguise is to run `histalign info <PATH TO A SAMPLE IMAGE>`. This will print out information about the image in question, among which the number of channels should be available. If you see there is more than a single channel, you are most likely in one of two positions:

1. Your images are actually grayscale but are multichannel with all but one channel being all zeros.
1. Your images are in fact RGB in disguise (as they appear grayscale in an image viewer) and a conversion is needed.

To find out which situation you are in, simple open the image in ImageJ and split the channels (`Image > Color > Split Channels`). If there is more than one channel with pixel values other than zero, you have RGB images. If only a single channel have non-zero values, you have truly grayscale images. This latter case is easy to fix using the `histalign split --on C <PATH TO YOUR IMAGE>` command which will split each channel of your image into a separate file. You can then only align the non-zero channel. If you have RGB images, you can either convert them with ImageJ (slowest but most accurate), or use the `histalign transform -t rgb2gray <PATH TO YOUR IMAGE>` command (most convenient but slightly worse results than ImageJ).

### Volume generation fails on MacOS

It appears that volume generation can fail when run on MacOS (see [#11](https://github.com/DuguidLab/histalign/issues/11)). A workaround is to use a Linux machine to generate the volume if you've done the alignment on a Mac.

Note that the path to your images as used during alignment will need to be the same when switching over to Linux. For example, if your images came from a directory under `/foo/bar` on Mac, that path will need to be the same on the Linux machine.

## License

`histalign` is distributed under the terms of the [MIT](https://spdx.org/licenses/MIT.html) license.


## References

The icons were taken from [UXWing](https://uxwing.com/).
