A typical workflow for `histalign` consists of four main steps:  

1. Data preparation  
2. Image registration  
3. Volume building  
4. Quantification/visualisation  

## [Data preparation](tutorials/data-preparation.md)

This step is arguably the most important.  
In order to get the most of `histalign`, you will need to make sure you data is organised the right way. This means images should be single-channel images, in a format [supported by `histalign`](reference/CLI/index.md#histalign-list).  
To have the smoothest experience with the app, you might also want to convert your data to HDF5 (even if it is already in a supported format) as that will reduce memory use for thumbnail generation and speed up image opening.

## [Image registration](tutorials/registration.md)

When you data is ready and organised properly, you can move on to the registration step.  

This is the main use of the application and you can use a mix of manual adjustments along with landmark registration to determine appropriate affine transforms to register images to the Allen CCF.

## [Volume building](tutorials/volume-building.md)

Once you have registered enough slices for a brain, you can move on to volume building. This generates a 3D volume from the registration data you provided by interpolating the sparse 3D reconstruction of your data.  

Usually, this is where you would move on to your own pipeline, but `histalign` also provides some basic quantification/visualisation.

## [Quantification](tutorials/quantifying.md)/[visualisation](tutorials/visualisation.md)

The final functionalities of `histalign` are quantification and visualisation.  
They are currently fairly basic, allowing you to measure the average 2D or 3D fluorescence of slices/volumes, and allowing a quick 2D or 3D quality assurance of registered slices/generated volumes.

Because the needs of different people/experiments will wildly differ, these two functionalities are there for convenience if your needs align with them but it is more likely that you will need to carry out your own quantification, in which case you can [export the generated volumes](tutorials/volume-building.md#exporting-3d-volumes).
