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

Data_Dir = '/home/ec2-user/BioSCape_across_scales/01_data/01_rawdata'
Out_Dir = '/home/ec2-user/BioSCape_across_scales/01_data/02_processed'
bucket_name = 'bioscape.gra'
s3 = boto3.client('s3')

def upload_to_s3(bucket_name, file_path, s3_key):
    """
    Upload a file from an EC2 instance to Amazon S3.

    :param bucket_name: Name of the S3 bucket
    :param file_path: Local path to the file on the EC2 instance
    :param s3_key: Destination key in the S3 bucket (e.g., folder/file_name.ext)
    """
    # Initialize the S3 client
    s3 = boto3.client('s3')

    try:
    # Upload the file
        s3.upload_file(file_path, bucket_name, s3_key)
        print(f'Successfully uploaded {file_path} to {bucket_name}/{s3_key}')
    except Exception as e:
        print(f"Error uploading file: {e}")

def clip_raster(src, minx, miny, maxx, maxy):
    geom = box(minx, miny, maxx, maxy)
    out_image, out_transform = rasterio.mask(src, [geom], crop=True)
    out_meta = src.meta.copy()
    out_meta.update({"driver": "GTiff", 
        "height": out_image.shape[1],
        "width": out_image.shape[2],
        "transform": out_transform})
    return out_image, out_meta

def download_shapefile(bucket, prefix, output_dir):
    # List all files with the given prefix
    files = s3.list_objects(Bucket=bucket, Prefix=prefix)['Contents']
                
    # Create the output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)                        
    
    downloaded_files = []
    # Download all files
    for file in files:
        key = file['Key']
        local_path = os.path.join(output_dir, os.path.basename(key))
        s3.download_file(bucket, key, local_path)
        downloaded_files.append(local_path)

    return downloaded_files


# Find files for mosaicing (define search terms)
#search_criteria1 = "20190515"
#search_criteria2 = "20190901_17"
#dirpath = "SERC_flightlines/"

# List objects in the S3 bucket in the matching directory
#objects = s3.list_objects_v2(Bucket=bucket_name, Prefix=dirpath)['Contents']
# Filter objects based on the search criteria
#files = [obj['Key'] for obj in objects if obj['Key'].endswith('.tif') and (search_criteria1 in obj['Key'])]
#print(files)
# Or select files based on QGIS identification
#files = ['TEAK_flightlines/20190901_164806_output_.tif']
# List shapefile prefices
#shapefiles = ['Site_boundaries/SERC/SERC_010_EPSG',
#              'Site_boundaries/SERC/SERC_009_EPSG',
#              'Site_boundaries/SERC/SERC_005_EPSG',
#              'Site_boundaries/SERC/SERC_004_EPSG',
#              'Site_boundaries/SERC/SERC_044_EPSG',
#              'Site_boundaries/SERC/SERC_012_EPSG',
#              'Site_boundaries/SERC/SERC_001_EPSG']

# Set config options
gdal.SetConfigOption('SHAPE_RESTORE_SHX', 'YES')
gdal.SetConfigOption('CHECK_DISK_FREE_SPACE', 'FALSE')

#for i, file in enumerate(files):
#    print('Loading file from S3')
#    s3.download_file(bucket_name, file, Out_Dir + '/file_' + str(i) + '.tif')
#    flight = Out_Dir + '/file_' + str(i) + '.tif'
#    print(flight)
#    with rasterio.open(flight) as src:
#        clipped_data, transform = rasterio.mask.mask(src, clip_polygon.geometry, crop=True)
#        clipped_dataset = rasterio.open('clipped_file_' + str(i) + '.tif', 'w', **src.profile)
#        print(clipped_dataset)
#        clipped_dataset.write(clipped_data)
#        datasets.append(clipped_dataset)
#print(datasets)
# Open in read mode and add to file list

src_files_to_mosaic = []
#for j,shape in enumerate(shapefiles):
#    
#    print(shape)
#
#    # Download shapefile files
#    downloaded_files = download_shapefile(bucket_name, shape, Out_Dir)
#    shapefile_path = next(file for file in downloaded_files if file.endswith('.shp'))
#    
#    # Open shapefile and access geometry
#    with fiona.open(shapefile_path, "r") as shapefile:
#        shapes = [feature["geometry"] for feature in shapefile]
#    
#    #minx, miny, maxx, maxy = box(*shapes[0].bounds).bounds
#    
#    # Access the bounds of the entire GeoDataFrame
#    gdf = gpd.read_file(shapefile_path)
#    #minx, miny, maxx, maxy = gdf.total_bounds
#    #print(minx, miny, maxx, maxy)
#
file_ID = ['5', '6']
for i,ID in enumerate(file_ID):
    
    # List files associated with a single buffer shape
    search_criteria = str(ID) + '_Clipped_file_'
    dirpath = "SERC_flightlines/Shape_"

    # List objects in the S3 bucket in the matching directory
    objects = s3.list_objects_v2(Bucket=bucket_name, Prefix=dirpath)['Contents']
    # Filter objects based on the search criteria
    files = [obj['Key'] for obj in objects if obj['Key'].endswith('.tif') and (search_criteria in obj['Key'])]
    print(files)
    for i,file in enumerate(files):
        flight  = Out_Dir + '/file_' + str(i) + '.tif'
        try:
            s3.download_file(bucket_name, file, flight)
            print(f"The file '{file}' exists.")
        except Exception as e:
            print(f"Error: {e}")
        src = rasterio.open(flight)
        src_files_to_mosaic.append(src)

    # Mosaic files
    print(src_files_to_mosaic)
    mosaic, out_trans = merge(src_files_to_mosaic, nodata = -9999)
    print('Merge complete')
    # Update metadata
    out_meta = src.meta.copy()
    print(out_meta)
    print(mosaic.shape)
    out_meta.update({"driver": "GTiff",
        "height": mosaic.shape[1],
        "width": mosaic.shape[2],
        "transform": out_trans,
        "crs": "+init=epsg:32618 +units=m +no_defs "})
    print(out_meta)

    # Write to computer, send to S3
    mosaic_name = Out_Dir + "/mosaic_SRER.tif"
    with rasterio.open(mosaic_name, "w", **out_meta) as dest:
        dest.write(mosaic)
    print("File written")
    
    # Push to S3 bucket
    destination_s3_key = 'SERC_flightlines/Mosaic_SERC_'+str(i)+'.tif'
    local_file_path = mosaic_name
    upload_to_s3(bucket_name, local_file_path, destination_s3_key)
    print("File uploaded to S3")
    
    # Remove unneeded files (mosaic and shapefile)
    os.remove(local_file_path)
    #os.remove(shape)

