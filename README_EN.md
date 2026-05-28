# openGauss-connector-python-psycopg2

## Overview

This repository is the Python driver for openGauss.

## Packaging Procedure

1. Python 3 is recommended. Install Python 3 and `python3-devel` on the server.

    ```shell
    yum install python3 python3-devel
    ```

2. The packaging of the Python driver depends on `libpq` compiled by `openGauss-server`. For details, see [openGauss Code Compilation](https://gitee.com/opengauss/openGauss-server#%E4%BD%BF%E7%94%A8%E5%91%BD%E4%BB%A4%E7%BC%96%E8%AF%91%E4%BB%A3%E7%A0%81).

3. Download the code of the `openGauss-connector-python-psycopg2` repository, go to the root directory, and run the following command:

    ```shell
    sh build.sh -bd /data/compile/openGauss-server/dest/ -v 5.0.0
    ```

    **Notes**
    -`bd`: specifies the build result directory of the openGauss database
    -`v`: specifies the version number of the build package. If this parameter is not specified, `5.0.0` is used.

    The compiled driver is stored in the `output` directory.

## Software Download

The community performs daily builds and provides three compiled driver packages for different environments. The download paths are as follows:

`<VERSION>` indicates the latest version number.

openEuler-AArch64:

`https://opengauss.obs.cn-south-1.myhuaweicloud.com/latest/arm/openGauss-<VERSION>-openEuler-aarch64-Python.tar.gz`

CentOS-x86_64:

`https://opengauss.obs.cn-south-1.myhuaweicloud.com/latest/x86/openGauss-<VERSION>-CentOS-x86_64-Python.tar.gz`

openEuler-x86_64:

`https://opengauss.obs.cn-south-1.myhuaweicloud.com/latest/x86_openEuler/openGauss-<VERSION>-openEuler-x86_64-Python.tar.gz`

Alternatively, download the released driver package of each version in the `openGauss Connectors` area on the [official website](https://opengauss.org/en/download/). After that, verify the integrity of the software package as follows:

(1) Calculate the SHA256 value of the downloaded package. (The following uses the 6.0.1 release package as an example. The operations for other versions are the same.)

~~~
sha256sum openGauss-Python-6.0.1-openEuler22.03-aarch64.tar.gz
~~~

(2) Copy the SHA256 value of the corresponding driver package in the `openGauss Connectors` section on the [official website](https://opengauss.org/en/download/). Compare it with the SHA256 value calculated in step (1). If they are consistent, the downloaded package is complete. Otherwise, download the package again.

## Instructions

### Installing psycopg2

After decompressing the installation package, you will obtain two directories: `lib` and `psycopg2`.

Copy and paste the `psycopg2` directory to the `site-packages` directory of the Python interpreter so that Python can index the directory.

Run the following command to locate the `site-packages` directory:

```shell
python -c "from distutils.sysconfig import get_python_lib;print(get_python_lib())"
# output: /usr/lib/python3.6/site-packages
```

After determining the location of the `site-packages` directory, copy and paste the entire `psycopg2` folder to this directory and grant permissions to other users.

```shell
cp -r psycopg2 [/path/to/site-packages/] && chmod 755 [/path/to/site-packages/]psycopg2
```

The other directory `lib` in the installation package contains the C dynamic library files, such as `libpq`, on which `psycopg2` depends.

The files in this directory may have the same names as the dynamic libraries of the system.

You are advised to store the application and the `lib` directory under a separate system user to isolate them from the system's built-in libraries, preventing other system tools from being affected.

Switch to the running user and run the following command:

```shell
echo "export LD_LIBRARY_PATH=[/path/to/lib]:$LD_LIBRARY_PATH" >> ~/.bashrc
source ~/.bashrc
```

The installation is now complete.

### Application Connection

```python
import psycopg2

# DSN format
conn = psycopg2.connect("postgres://user:password@ip1:port,ip2:port:.../dbname?target_session_attrs=[any|read-write]")
# Key-value format
conn = psycopg2.connect(host="ip1[,ip2]",
                        port=port1,
                        database=db,
                        user=user,
                        password=password,
                        target_session_attrs="read-write")
```

## Contributions

1. Fork this repository.
2. Create a Feat_xxx branch.
3. Commit the code.
4. Create a pull request.
