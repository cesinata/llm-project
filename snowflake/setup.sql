-- Run in a Snowsight SQL worksheet as ACCOUNTADMIN (the default role on a trial account).
-- Step 1 creates the raw table and a stage; step 2 is uploading the CSV to the stage in the
-- Snowsight UI; step 3 copies it into the table. All columns are text, as in DuckDB, so every
-- cast happens in dbt.

-- 1. Database, schema, raw table and stage
create database if not exists crashsql;
create schema if not exists crashsql.raw;
use schema crashsql.raw;

create or replace table crashes (
    ACCIDENT_NO varchar,
    ACCIDENT_DATE varchar,
    ACCIDENT_TIME varchar,
    ACCIDENT_TYPE varchar,
    DAY_OF_WEEK varchar,
    DCA_CODE varchar,
    DCA_CODE_DESCRIPTION varchar,
    LIGHT_CONDITION varchar,
    POLICE_ATTEND varchar,
    ROAD_GEOMETRY varchar,
    SEVERITY varchar,
    SPEED_ZONE varchar,
    RUN_OFFROAD varchar,
    ROAD_NAME varchar,
    ROAD_TYPE varchar,
    ROAD_ROUTE_1 varchar,
    LGA_NAME varchar,
    DTP_REGION varchar,
    LATITUDE varchar,
    LONGITUDE varchar,
    VICGRID_X varchar,
    VICGRID_Y varchar,
    TOTAL_PERSONS varchar,
    INJ_OR_FATAL varchar,
    FATALITY varchar,
    SERIOUSINJURY varchar,
    OTHERINJURY varchar,
    NONINJURED varchar,
    MALES varchar,
    FEMALES varchar,
    BICYCLIST varchar,
    PASSENGER varchar,
    DRIVER varchar,
    PEDESTRIAN varchar,
    PILLION varchar,
    MOTORCYCLIST varchar,
    UNKNOWN varchar,
    PED_CYCLIST_5_12 varchar,
    PED_CYCLIST_13_18 varchar,
    OLD_PED_65_AND_OVER varchar,
    OLD_DRIVER_75_AND_OVER varchar,
    YOUNG_DRIVER_18_25 varchar,
    NO_OF_VEHICLES varchar,
    HEAVYVEHICLE varchar,
    PASSENGERVEHICLE varchar,
    MOTORCYCLE varchar,
    PT_VEHICLE varchar,
    DEG_URBAN_NAME varchar,
    SRNS varchar,
    RMA varchar,
    DIVIDED varchar,
    STAT_DIV_NAME varchar
);

create or replace file format crash_csv
    type = csv
    skip_header = 1
    field_optionally_enclosed_by = '"'
    empty_field_as_null = true;

create or replace stage crash_stage file_format = crash_csv;

-- 2. In Snowsight: Data > Databases > CRASHSQL > RAW > Stages > CRASH_STAGE > + Files,
--    then upload data/raw/victorian_road_crash_data.csv.

-- 3. Load and check: expect 202,554 rows.
copy into crashes from @crash_stage file_format = (format_name = crash_csv);
select count(*) from crashes;

-- 4. Optional, for key-pair login from dbt (see README). Paste the public key without its
--    BEGIN/END lines, then check that RSA_PUBLIC_KEY_FP is set.
-- alter user <your_user> set rsa_public_key = 'MIIBIjANBgkqh...';
-- desc user <your_user>;
