import rasterio
from rasterio.merge import merge
from rasterio.plot import show
from rasterio.mask import mask
from rasterio.warp import transform_bounds
from rasterio.transform import from_origin
from rasterio.warp import calculate_default_transform, reproject
import glob
import os
import boto3
from botocore.exceptions import NoCredentialsError, PartialCredentialsError, ClientError
from shapely.geometry import box
import geopandas as gpd
import fiona
from fiona.crs import from_epsg
import pycrs
from osgeo import gdal
import numpy as np
from S01_Functions import * # add scripts folder to python path manager

Data_Dir = '/home/ec2-user/BioSCape_across_scales/01_data/01_rawdata'
Out_Dir = '/home/ec2-user/BioSCape_across_scales/01_data/02_processed'
bucket_name = 'bioscape.gra'
s3 = boto3.client('s3')

# Set config options
gdal.SetConfigOption('SHAPE_RESTORE_SHX', 'YES')
gdal.SetConfigOption('CHECK_DISK_FREE_SPACE', 'FALSE')

def pre121_max(old_data, new_data, old_nodata, new_nodata, **kwargs):
    mask = np.logical_and(~old_nodata, ~new_nodata)
    old_data[mask] = np.maximum(old_data[mask], new_data[mask])
    mask = np.logical_and(old_nodata, ~new_nodata)
    old_data[mask] = new_data[mask]

src_files_to_mosaic = []

file_ID = [
           '001',
           '002',
           '009',
           '012',
           '013',
           '020',
           '026',
           '027',
           '032',
           '044'
           ]

for i,ID in enumerate(file_ID):
    src_files_to_mosaic = []
    # List files associated with a single buffer shape
    search_criteria = str(ID)
    dirpath = "TALL_flightlines/Site_boundaries/TALL/"

    # List objects in the S3 bucket in the matching directory
    objects = s3.list_objects_v2(Bucket=bucket_name, Prefix=dirpath)['Contents']
    # Filter objects based on the search criteria
    files = [obj['Key'] for obj in objects if obj['Key'].endswith('.tif') and (search_criteria in obj['Key'])]
    print(files)
    for j,file in enumerate(files):
        flight  = Out_Dir + '/file_' + str(j) + '.tif'
        try:
            s3.download_file(bucket_name, file, flight)
            print(f"The file '{file}' exists.")
        except Exception as e:
            print(f"Error: {e}")

        with rasterio.open(flight) as src:
            # Read raster as array
            array = src.read()
            # Convert nodata values to 0 (assumes nodata values are set correctly in the metadata)
            nodata = src.nodata
            print(nodata)
            if nodata is not None:
                array[array == nodata] = 0
            else:
                # Consider what to do if nodata is not defined, or define a default action
                print("nodata is not defined")

            # Define modified file path
            modified_flight = Out_Dir + '/modified_file_' + str(j) + '.tif'

            # Update metadata for the modified file
            out_meta = src.meta.copy()
            out_meta.update({
                "nodata": 0  # Ensure nodata is now set to 0 in the metadata
            })

            # Write modified array to new TIFF
            with rasterio.open(modified_flight, "w", **out_meta) as dest:
                dest.write(array)
        modified_src = rasterio.open(modified_flight)
        src_files_to_mosaic.append(modified_src)

    # Mosaic files
    print(src_files_to_mosaic)
    mosaic, out_trans = merge(src_files_to_mosaic, method = pre121_max)
    print('Merge complete')
    # Update metadata
    out_meta = src.meta.copy()
    print(out_meta)
    print(mosaic.shape)
    out_meta.update({"driver": "GTiff",
        "height": mosaic.shape[1],
        "width": mosaic.shape[2],
        "transform": out_trans,
        "crs": "+init=epsg:32616 +units=m +no_defs "}) # for TALL UTM WGS 16N
    print(out_meta)

    # Write to computer, send to S3
    local_file_path = Out_Dir + "/mosaic_TALL.tif"
    with rasterio.open(local_file_path, "w", **out_meta) as dest:
        dest.write(mosaic)
    print("File written")
    
    # Push to S3 bucket
    destination_s3_key = 'TALL_flightlines/Mosaic_TALL_'+str(ID)+'.tif'
    upload_to_s3(bucket_name, local_file_path, destination_s3_key)
    print("File uploaded to S3")
    
    # Remove unneeded files (mosaic and shapefile)
    os.remove(local_file_path)
    mosaic = None
    src_files_to_mosaic = None 
