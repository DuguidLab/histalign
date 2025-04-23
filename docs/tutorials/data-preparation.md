# First things first: preparing your data

The first thing you need to do, even before starting the application GUI, is to preprocess your data. `histalign` assumes the data provided is ready for analysis.

Another thing that needs to be done before starting the registration process is to ensure you data is in a form the application will understand. This means that images you wish to align should have a single channel (i.e., only X and Y dimensions are allowed). If you are not sure whether your images are two dimensional, you can run the command `histalign info` on a file. This will print a lot of information but the portion you care about here is the `DimensionOrder`. If the order only contains X and Y, you are good to proceed. If there are extra dimensions, you will need to either split or project your data using the `histalign split` and `histalign project` commands respectively.


## Data organisation

Before working through these commands if you need them, you should decide where the files that `histalign` will need should live. If you wish to register 2D stack projections but build a volume using the full Z-stacks, they will need to be in the same directory. Similarly, if you wish to register using channel A but run quantification using channel B, both files should be in the same directory.  

The most important part for now, is to ensure the images required for registration are all in the same folder. If you later decide you want to run quantification on full stacks or different channels, those extra files can be added to the folder used for registration. `histalign` can then be directed to replace or truncate portions of file names to find the related files.


## Splitting multi-channel files

If your files require splitting because they have multiple channels, the [`histalign split`](../reference/CLI/index.md#histalign-split) command is what you need.  

In order to split files, you should locate the [absolute path](https://en.wikipedia.org/wiki/Path_(computing)) to your images (i.e, the path starting from the root of your file system). It is also possible to pick a different output directory to keep a logical separation between different dimension orders. Once you have those paths, you should be able to simply run the following command:

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


## What's next?

Once your data is properly split/projected, you can move on to [creating your first project](your-first-project.md).
