# First things first: preparing your data

The first thing you need to do, even before starting the application GUI, is to preprocess your data. `histalign` assumes the data provided is ready for analysis.

Another thing that needs to be done before starting the registration process is to ensure you data is in a form the application will understand. This means that images you wish to align should have a single channel (i.e., only X and Y dimensions are allowed). If you are not sure whether your images are two dimensional, you can run the command `histalign info` on a file. This will print a lot of information but the portion you care about here is the `DimensionOrder`. If the order only contains X and Y, you are good to proceed. If there are extra dimensions, you will need to either split or project your data using the `histalign split` (if C is in the dimension order) and `histalign project` (if Z is in the dimension order) commands respectively.


!!! Note
    To more easily follow this tutorial, you should make sure you known what [absolute and relative paths](https://en.wikipedia.org/wiki/Path_(computing)) are.  
    As a brief explanation, relative paths start with a file or folder name (i.e., no leading `/` on Linux/macOS, and no `DRIVE_LETTER:\` on Windows). Absolute paths, on the other hand, start from the root of the file system and will have a leading `/` on Linux/macOS and a drive letter on Windows (e.g., `C:\`).

    The command examples in this tutorial will be working with absolute paths as that tends to prevent the most common types of errors.


## Converting to HDF5

This is a starting step that is not necessary but highly recommended. This will speed up both the splitting/projecting, and the GUI once you start the registration process.

In order to convert files to HDF5, you can use the [`histalign convert`](../reference/CLI/index.md#histalign-convert) command.  
To convert files from a supported format to HDF5, you would run the following command:

```bash
histalign convert --from $EXT --to H5 $ABSOLUTE_PATH$
```

where:  

- `EXT` is the extension of your files (e.g., .tif, .h5),
- `ABSOLUTE_PATH` is the absolute path to your image folder.

## Data organisation

Before working through these commands if you need them, you should decide where the files that `histalign` will need should live. If you wish to register 2D stack projections but build a volume using the full Z-stacks, they will need to be in the same directory. Similarly, if you wish to register using channel A but run quantification using channel B, both files should be in the same directory.  

The most important part for now, is to ensure the images required for registration are all in the same folder. If you later decide you want to run quantification on full stacks or different channels, those extra files can be added to the folder used for registration. `histalign` can then be directed to replace or truncate portions of file names to find the related files.


## Splitting multi-channel files

If your files require splitting because they have multiple channels, the [`histalign split`](../reference/CLI/index.md#histalign-split) command is what you need.  

In order to split files, you should locate the absolute path to your images. Once you have it, you should be able to simply run the following command:

```shell
histalign split $ABSOLUTE_PATH$ --on C --extension $EXT$
```

where:  

- `ABSOLUTE_PATH` is the absolute path to your image folder,  
- `EXT` is the file extension of your images (e.g., .tiff, .h5).


## Projecting Z-stacks

Similar to `histalign split`, there is a [`histalign project`](../reference/CLI/index.md#histalign-project) command to project Z-stacks.

To project stacks using maximum intensity projection, you would therefore run:

```shell
histalign project $ABSOLUTE_PATH$ --type max --extension $EXT$ 
```

where:  

- `ABSOLUTE_PATH` is the absolute path to your stack folder,  
- `EXT` is the file extension of your stacks (e.g., .tiff, .h5).  


## Recommended structure

Let's say you have done an experiment (called `ABC`) and have acquired histology image for two subjects (`123` and `456`) saved as TIFF files.  
The recommended structure would follow something along these lines:

```bash
expABC
├── sub123
│   ├── slice1.tif
│   ├── slice2.tif
│   └── ...
└── sub456
    ├── slice1.tif
    ├── slice2.tif
    └── ...
```

If your images are already single-channel, you are good to start. However, we recommend converting over to HDF5 as that will make the application more responsive (faster thumbnails, and faster image loading for registration).  

### With multi-channel

If your images are multi-channel (let's say they have 3 channels), after running [the above instructions](#splitting-multi-channel-files), you would end up with the following file structure:

```bash
expABC
├── sub123
│   ├── slice1.tif
│   ├── slice1_C0.tif
│   ├── slice1_C1.tif
│   ├── slice1_C2.tif
│   ├── slice2.tif
│   ├── slice2_C0.tif
│   ├── slice2_C1.tif
│   ├── slice2_C2.tif
│   └── ...
└── sub456
    ├── slice1.tif
    ├── slice1_C0.tif
    ├── slice1_C1.tif
    ├── slice1_C2.tif
    ├── slice2.tif
    ├── slice2_C0.tif
    ├── slice2_C1.tif
    ├── slice2_C2.tif
    └── ...
```

### With Z-stacks

If instead, your images are Z-stacks (that you project using the maximum intensity), after running [the above instructions](#projecting-z-stacks), you would end up with the following file structure:

```bash
expABC
├── sub123
│   ├── slice1.tif
│   ├── slice1_max.tif
│   ├── slice2.tif
│   ├── slice2_max.tif
│   └── ...
└── sub456
    ├── slice1.tif
    ├── slice1_max.tif
    ├── slice2.tif
    ├── slice2_max.tif
    └── ...
```

### With both

Now, combining the two (projecting then splitting), your structure would end up like so:

```bash
expABC
├── sub123
│   ├── slice1.tif
│   ├── slice1_max.tif
│   ├── slice1_max_C0.tif
│   ├── slice1_max_C1.tif
│   ├── slice1_max_C2.tif
│   ├── slice2.tif
│   ├── slice2_max.tif
│   ├── slice2_max_C0.tif
│   ├── slice2_max_C1.tif
│   ├── slice2_max_C2.tif
│   └── ...
└── sub456
    ├── slice1.tif
    ├── slice1_max.tif
    ├── slice1_max_C0.tif
    ├── slice1_max_C1.tif
    ├── slice1_max_C2.tif
    ├── slice2.tif
    ├── slice2_max.tif
    ├── slice2_max_C0.tif
    ├── slice2_max_C1.tif
    ├── slice2_max_C2.tif
    └── ...
```

This way, you can have your raw Z-stack, multi-channel data in the same folder as your single-channel images and `histalign` will only pick up the single-channel ones for registration.

## What's next?

Once your data is properly split/projected, you can move on to [creating your first project](your-first-project.md).
