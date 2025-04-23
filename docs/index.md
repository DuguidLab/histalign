# Getting started

[`histalign`](https://github.com/DuguidLab/histalign) is an open-source package that facilitates the registration of two-dimensional histological slices to the [Allen Institute's Common Coordinate Framework](https://www.sciencedirect.com/science/article/pii/S0092867420304025?via%3Dihub) (CCF) for 2D and 3D quantification and visualisation. It provides a graphical user interface (GUI) to permit the user to apply any combination of [affine transformations](https://en.wikipedia.org/wiki/Affine_transformation#Image_transformation) to images obtained through experiments in order to register them to the Allen Institute's Mouse Brain Atlas.

## Prerequisites
`histalign` works best with [HDF5 files](https://www.hdfgroup.org/solutions/hdf5/) (.h5). However, support for TIFF, LIF, and PNG files is available. For a full list of available formats, run the `histalign list` command locally. 

In order to carry out alignment, single-channel, two-dimensional images are needed. See [data preparation](tutorials/data-preparation.md) for more details.  
It should also be noted that only bright tissue on dark background is supported. The quantification pipeline should be able to handle dark on bright but the alignment experience will be much degraded. 

## Installation
`histalign` is being developed with all major platforms in mind (Linux, macOS, Windows). However, due to hardware issues, testing on MacOS is limited. 

The recommended way to install `histalign` is to use [`pipx`](https://pipx.pypa.io/latest/). These instructions will guide you through installing both `pipx` and `histalign`.  

If you run into troubles when trying to install `pipx`, refer to the latest documentation from [their website](https://pipx.pypa.io/latest/installation/#installing-pipx) to see if it fixes the problem. If you run into troubles when trying to install `histalign` itself, have a look at the [open and closed issues](https://github.com/DuguidLab/histalign/issues?q=is%3Aissue%20state%3Aclosed) on the package's GitHub. If you do not find an answer after looking through those, feel free to [open a new one](https://github.com/DuguidLab/histalign/issues/new), detailing your problem as best you can.

### Installing `pipx`

#### On Linux

##### Ubuntu 23.04 or above

```shell
sudo apt update
sudo apt install pipx
pipx ensurepath
```

##### Fedora

```shell
sudo dnf install pipx
pipx ensurepath
```
##### Other distributions (using `pip`)

```shell
python3 -m pip install --user pipx
python3 -m pipx ensurepath
```

#### On macOS

```shell
brew install pipx
pipx ensurepath
```

#### On Windows

On Windows, the recommended way to run `histalign` is using the [Windows Subsystem for Linux](https://learn.microsoft.com/en-us/windows/wsl/install) (WSL). If you do not have it enabled and do not wish to do so, you can follow the rest of these instructions. If you wish to continue with WSL, install `pipx` using the [Linux instructions](#on-linux) above.

The recommended way to install `pipx` on Windows is using [Scoop](https://scoop.sh/). Once Scoop is installed, run the following commands.

```shell
scoop install pipx
pipx ensurepath
```

However, you can also install it using `pip`:

```shell
python3 -m pip install --user pipx
```

### Installing `histalign`

Once `pipx` has been installed, run the following command:

```shell
pipx install histalign
```

And that should be you sorted! From there, running `histalign` from the command line should start the application GUI.

## What's next?

For your first time working with the app, you should start by reading the [tutorials](tutorials/index.md) section which guide you through the interface and what a typical workflow looks like when using `histalign`.  

For typical uses of the application, see the [how-to guides]().

For documentation of the `histalign` API to use in your own project, see the [reference]() section.

For more in-depth guides to each step of the workflow, see the [tutorials](tutorials/index.md)
