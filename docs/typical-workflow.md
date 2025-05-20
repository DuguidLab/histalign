A typical workflow for `histalign` consists of three main steps:  
1. Data preparation  
2. Image registration  
3. Volume building

## [Data preparation](tutorials/data-preparation.md)

This step is arguably the most important.  
In order to get the most of `histalign`, you will need to make sure you data is organised the right way. This means images should be single-channel images, in a format [supported by `histalign`](reference/CLI/index.md#histalign-list).  
To have the smoothest experience with the app, you might also want to convert your data to HDF5 (even if it is already in a supported format) as that will reduce memory use for thumbnail generation and speed up image opening.

## [Image registration](tutorials/registration.md)

When you data is ready and organised properly, you can move on to the registration step.  

This is the main use of the application and you can use a mix of manual adjustments along with landmark registration to determine appropriate affine transforms to register images to the Allen CCF.

## [Volume building](tutorials/volume-building.md)

Once you have registered enough slices for a brain, you can move on to volume building. This generates a 3D volume from the registration data you provided by interpolating the sparse 3D reconstruction of your data.  

This is typically the last step the application is used for as workflows very wildly for different users and you are free to export the raw and interpolated volumes to carry out further analysis yourself. How to work with the volumes is documented in the [export function tutorial](tutorials/volume-building.md#exporting-3d-volumes).  
However, `histalign` can also be used for [average fluorescence quantification](tutorials/quantifying.md) and basic [2D and 3D visualisation](tutorials/visualisation.md).
