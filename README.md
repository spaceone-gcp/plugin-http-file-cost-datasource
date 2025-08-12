# plugin-http-file-cost-datasource

* Plugin for collecting cost data from **CSV file**

---

## 1) Overview
ㅡ
This plugin is a plugin that collects cost data from a CSV file.  
The CSV file must be in the format specified in the [2) CSV format](#2-csv-format) section.  

The CSV file must be located on the web server,  
and the URL must be specified in the [3) options of the plugin](#3-options-of-plugin).  

If you have completed understanding the steps 2) and 3),  
you can check the actual usage in [4) How to use](#4-how-to-use).

## 2) CSV format

![img.png](examples/img.png)

* The above is an example of a csv file, and the fields that exist in the csv must exist.  
* Here is a list of available fields. Of these, `cost` fields are required field.  
* The required date fields are:  
  * If there is a `billed_date` (ex. "2023-09-01") field, it works even if there are no `year` and `month` fields.
  * This works if there is no `billed_date` field and there are `year`, `month`, and `day` fields.
  * If there is no `billed_date` field and there are `year` and `month`, `day` is applied as 1 day.
  * Does not work except for the above cases.

### Supported CSV Formats

* **Delimiters**: The plugin automatically detects common delimiters including comma (,), semicolon (;), tab (\t), and pipe (|)
* **Encoding**: UTF-8, UTF-8-BOM, and other encodings are automatically detected
* **Headers**: CSV files must have a header row with column names
* **Data Requirements**: Files must contain at least one data row (not just headers)

### Error Handling

The plugin includes robust error handling for common CSV parsing issues:

* **Empty Files**: Returns clear error message when files contain no data
* **Missing Headers**: Detects and reports files without proper column headers
* **Invalid Delimiters**: Automatically detects and uses appropriate delimiters
* **Encoding Issues**: Handles various character encodings gracefully
* **Malformed Data**: Skips bad lines and continues processing valid data
* **File Download Issues**: Validates file downloads and reports failures
* **Temporary File Management**: Automatically cleans up temporary files after processing
* **Filename Sanitization**: Handles special characters and long filenames safely

### Recent Improvements

The plugin has been enhanced with better file handling capabilities:

* **Enhanced File Validation**: 
  - Validates file downloads before processing
  - Checks file size to ensure non-empty files
  - Provides detailed error messages for file-related issues

* **Improved Filename Handling**:
  - Safely handles filenames with special characters
  - Uses hash-based naming for very long filenames
  - Prevents file system compatibility issues

* **Automatic Resource Cleanup**:
  - Automatically removes temporary files after processing
  - Prevents disk space accumulation
  - Includes error handling for cleanup operations

* **Better Error Reporting**:
  - More specific error messages for different failure scenarios
  - Detailed logging for debugging file processing issues
  - Clear distinction between different types of file errors

<br>

* **cost (required)**
* **billed_date (required)**
* **year (required)**
* **month (required)**
* **day (optional)**
* usage_quantity
* usage_type
* provider
* region_code
* product

## 3) Options of plugin

* The following options are available for the plugin.
* The options are specified in the form of a YAML file.
* You can find out how yaml is used in [4) How to use](#4-how-to-use) section.
* An example using all options is shown below.
  ```yaml
  # update_data_source_options.yml
  ---
  options:
    base_url:
    - https://raw.githubusercontent.com/cloudforet-io/plugin-http-file-cost-datasource/master/examples/cost_example.csv
    - https://raw.githubusercontent.com/cloudforet-io/plugin-http-file-cost-datasource/master/examples/custom_cost_example.csv
    - https://raw.githubusercontent.com/cloudforet-io/plugin-http-file-cost-datasource/master/examples/example_with_billed_at.csv
    - https://raw.githubusercontent.com/cloudforet-io/plugin-http-file-cost-datasource/master/examples/examples_of_different_headers.csv
    field_mapper:
      cost: TotalCost
      currency: CurrencyCode
      day: Day
      month: Month
      provider: Provider
      usage_quantity: UsageQuantity
      usage_type: UsageType
      year: Year
    default_vars:
      currency: KRW
    billed_at: UsageStartDate
  ```

**base_url (required)**

* The URL of the CSV file to be used.
* The URL must be a list type.

```yaml
---
options:
  base_url:
    - https://raw.githubusercontent.com/cloudforet-io/plugin-http-file-cost-datasource/master/examples/cost_example.csv
    - https://raw.githubusercontent.com/cloudforet-io/plugin-http-file-cost-datasource/master/examples/custom_cost_example.csv
    - https://raw.githubusercontent.com/cloudforet-io/plugin-http-file-cost-datasource/master/examples/example_with_billed_at.csv
    - https://raw.githubusercontent.com/cloudforet-io/plugin-http-file-cost-datasource/master/examples/examples_of_different_headers.csv
```

**field_mapper (optional)**

* The field name of the CSV file to be used.
* If you do not specify this option, the [default column](#2-csv-format) is used.
* As you can see in [examples_of_different_headers.csv](examples/examples_of_different_headers.csv), if the column names
  are different, you can use these options to map them.

```yaml
---
options:
  field_mapper:
    cost: TotalCost
    currency: CurrencyCode
    day: Day
    month: Month
    provider: Provider
    usage_quantity: UsageQuantity
    usage_type: UsageType
    year: Year
```

**default_vars (optional)**

* If you want to set a default value for a field, you can use this option.
* If you do not specify this option, the [default column](#2-csv-format) is used.
* As you can see in [example_of_default_vars.csv](examples/example_of_default_vars.csv), This can be used if you want to
  default all currencies to KRW.

```yaml
---
options:
  default_vars:
    currency: KRW
```

## 4) How to use (Deprecated)

In order to use the plugin, how to use [spacectl CLI tools](https://github.com/cloudforet-io/spacectl) must be preceded.

1. Check if the plugin you want to use from the marketplace exists.

```shell
$ spacectl list repository.Plugin -p service_type=cost_analysis.DataSource --minimal

plugin_id                        | name                                | image                                     | state   | service_type             | registry_type
----------------------------------+-------------------------------------+-------------------------------------------+---------+--------------------------+-----------------
plugin-http-file-cost-datasource | HTTP file Cost Analysis Data Source | pyengine/plugin-http-file-cost-datasource | ENABLED | cost_analysis.DataSource | DOCKER_HUB
```

2. Register with the DataSource resource of cost-analysis.

```shell
$ spacectl exec register cost-analysis.DataSource -f register_data_source.yml
```

```yaml
# register_data_source.yml
---
name: HTTP File Data Source
service_type: EXTERNAL
image: pyengine/plugin-http-file-cost-datasource
tags: { }
template: { }
```

3. Check the registered CSV Plugin information.

```shell
$ spacectl exec get cost-analysis.DataSource -p data_source_id=<data_source_id>

---
created_at: '2023-02-06T11:04:34.348Z'
data_source_id: ds-123456789012
data_source_type: EXTERNAL
domain_id: domain-123456789012
last_synchronized_at: '2023-02-06T16:00:08.356Z'
name: HTTP File Data Source
plugin_info:
  metadata:
    data_source_rules:
    - actions:
        match_service_account:
          source: account
          target: data.account
      conditions: []
      conditions_policy: ALWAYS
      name: match_service_account
      options:
        stop_processing: true
      tags: {}
  plugin_id: plugin-http-file-cost-datasource
  upgrade_mode: AUTO
  version: 1.0.0.20230206.225536
state: ENABLED
tags: {}
template: {}
```

4. Sets the options corresponding to the url where the csv file is located in the plugin.

```shell
$ spacectl exec update_plugin cost-analysis.DataSource -p data_source_id=<data_source_id> -f update_data_source_options.yml
```

```yaml
# update_data_source_options.yml
---
options:
  base_url:
  - https://raw.githubusercontent.com/cloudforet-io/plugin-http-file-cost-datasource/master/examples/cost_example.csv
  - https://raw.githubusercontent.com/cloudforet-io/plugin-http-file-cost-datasource/master/examples/custom_cost_example.csv
  - https://raw.githubusercontent.com/cloudforet-io/plugin-http-file-cost-datasource/master/examples/example_with_billed_at.csv
  - https://raw.githubusercontent.com/cloudforet-io/plugin-http-file-cost-datasource/master/examples/examples_of_different_headers.csv
  field_mapper:
    cost: TotalCost
    currency: CurrencyCode
    day: Day
    month: Month
    provider: Provider
    usage_quantity: UsageQuantity
    usage_type: UsageType
    year: Year
  default_vars:
    currency: KRW
  billed_at: UsageStartDate
```

5. Manually sync the cost information of the csv file in step 4.

```shell
$ spacectl exec sync cost-analysis.DataSource -p data_source_id=<data_source_id>
```

## 5) Troubleshooting

### Common Error Messages and Solutions

#### ERROR_EMPTY_FILE: File is empty
**Cause**: The downloaded file contains no data or has zero bytes. This can occur due to:
- Empty blob in Google Cloud Storage
- Failed file download
- Corrupted file during transfer
- File path issues with special characters

**Solution**: 
- Check if the source file actually contains data
- Verify the URL is accessible and returns content
- Ensure the file format is supported (CSV or JSON)
- Check the blob size in Google Cloud Storage
- Verify file permissions and access rights
- Look for detailed error logs that include blob information and file paths

#### ERROR_NO_DATA_ROWS: File has no data rows
**Cause**: The file contains only headers or is malformed.
**Solution**:
- Verify the file has at least one data row after the header
- Check if the file format is correct
- Ensure proper line endings

#### ERROR_EMPTY_HEADER: Empty header line
**Cause**: The first line of the file is empty or contains only whitespace.
**Solution**:
- Check the file structure and ensure the first line contains column headers
- Remove any empty lines at the beginning of the file

#### ERROR_NO_DATA_FOUND: No data found in CSV file
**Cause**: The file was parsed but no valid data records were found.
**Solution**:
- Verify the file contains valid data rows
- Check for encoding issues
- Ensure the delimiter is correctly detected

#### ERROR_NO_COLUMNS: No columns to parse from file
**Cause**: The file has no recognizable column structure.
**Solution**:
- Check if the file is in the correct format
- Verify the delimiter is supported (comma, semicolon, tab, pipe)
- Ensure the file is not corrupted

#### ERROR_CSV_PARSING: CSV parsing error
**Cause**: The file format is not compatible with CSV parsing.
**Solution**:
- Check if the file is actually a CSV file
- Verify the encoding (UTF-8 recommended)
- Look for malformed lines or special characters

### Debugging Tips

1. **Check Logs**: Look for detailed error messages in the plugin logs that now include:
   - Blob information (size, content type, name)
   - File path details and safe filename generation
   - Download status and file existence checks
   - Temp directory information

2. **Verify File Access**: Ensure the plugin can access the file URL or Google Cloud Storage bucket

3. **Test File Format**: Try opening the file in a text editor to verify its structure

4. **Check File Size**: Ensure the file is not empty or corrupted

5. **Validate Encoding**: Make sure the file uses a supported encoding (UTF-8 recommended)

6. **Google Cloud Storage Specific**:
   - Verify blob exists and has content
   - Check bucket permissions and access rights
   - Ensure blob name doesn't contain problematic characters
   - Verify the blob is not a directory marker

7. **File Path Issues**: 
   - Check for special characters in file names
   - Verify temp directory permissions
   - Look for path length limitations