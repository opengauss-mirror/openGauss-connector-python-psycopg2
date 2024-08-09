#!/bin/bash
#######################################################################
# Copyright (c): 2020-2025, Huawei Tech. Co., Ltd.
# descript: Compile and pack python driver for openGauss
#           Return 0 means OK.
#           Return 1 means failed.
# version:  2.0
# date:     2020-08-09
#######################################################################
declare install_package_format='tar'
declare serverlib_dir='None'

#detect platform information.
PLATFORM=$(uname -p)

#get OS distributed version.
if [ -f "/etc/euleros-release" ]; then
    kernel=$(cat /etc/euleros-release | awk -F ' ' '{print $1}' | tr A-Z a-z)
    version=$(cat /etc/euleros-release | awk -F '(' '{print $2}'| awk -F ')' '{print $1}' | tr A-Z a-z)
elif [ -f "/etc/openEuler-release" ]; then
    kernel=$(cat /etc/openEuler-release | awk -F ' ' '{print $1}' | tr A-Z a-z)
    version=$(cat /etc/openEuler-release | awk -F '(' '{print $2}'| awk -F ')' '{print $1}' | tr A-Z a-z)
elif [ -f "/etc/centos-release" ]; then
    kernel=$(cat /etc/centos-release | awk -F ' ' '{print $1}' | tr A-Z a-z)
    version=$(cat /etc/centos-release | awk -F '(' '{print $2}'| awk -F ')' '{print $1}' | tr A-Z a-z)
elif [ -f "/etc/kylin-release" ]; then
    kernel=$(cat /etc/kylin-release | awk -F ' ' '{print $1}' | tr A-Z a-z)
    version=$(cat /etc/kylin-release | awk '{print $6}' | tr A-Z a-z)
else
    kernel=$(lsb_release -d | awk -F ' ' '{print $2}'| tr A-Z a-z)
    version=$(lsb_release -r | awk -F ' ' '{print $2}')
fi

if [ X"$kernel" == X"euleros" ]; then
    dist_version="Euler"
elif [ X"$kernel" == X"centos" ]; then 
    dist_version="CentOS"
elif [ X"$kernel" == X"openeuler" ]; then 
    dist_version="openEuler"
elif [ X"$kernel" == X"kylin" ]; then
    dist_version="Kylin"
elif [ X"$kernel" = X"redflag" ]; then
    dist_version="Asianux"
elif [ X"$kernel" = X"asianux" ]; then
    dist_version="Asianux"
else
    echo "We only support EulerOS, openEuler(aarch64), CentOS and Asianux platform."
    echo "Kernel is $kernel"
    exit 1
fi
os_version=$(cat /etc/os-release | grep -w VERSION_ID | awk -F '"' '{print $2}')

#######################################################################
## print help information
#######################################################################
function print_help()
{
    echo "Usage: $0 [OPTION]
    -h|--help              show help information.
    -bd|--serverlib_dir    the directory of sever binarylibs.
    -v|--version           package version number.
"
}

##default install version storage path
declare db_name_for_package='openGauss-Python'
declare version_number='6.0.0'

if [ $# = 0 ] ; then 
    echo "missing option"
    print_help 
    exit 1
fi

LOCAL_PATH=${0}
FIRST_CHAR=$(expr substr "$LOCAL_PATH" 1 1)
if [ "$FIRST_CHAR" = "/" ]; then
    LOCAL_PATH=${0}
else
    LOCAL_PATH="$(pwd)/${LOCAL_PATH}"
fi

LOCAL_DIR=$(dirname "${LOCAL_PATH}")
#########################################################################
##read command line paramenters
#######################################################################
while [ $# -gt 0 ]; do
    case "$1" in
        -h|--help)
            print_help
            exit 1
            ;;
        -bd|--serverlib_dir)
            if [ "$2"X = X ]; then
                echo "no given binarylib directory values"
                exit 1
            fi
            serverlib_dir=$2
            shift 2
            ;;
        -v|--version)
            if [ "$2" != "" ]; then
                echo "Package openGauss python driver version is : $2"
                version_number=$2
            else
                echo "No version number was specified. Use the default $version_number"
            fi
            shift 2
            ;;
         *)
            echo "Internal Error: option processing error: $1" 1>&2  
            echo "please input right paramtenter, the following command may help you"
            echo "./build.sh --help or ./build.sh -h"
            exit 1
    esac
done

#######################################################################
## declare all package name
#######################################################################
declare version_string="${db_name_for_package}-${version_number}"
declare package_pre_name="${version_string}-${dist_version}${os_version}-${PLATFORM}"
declare python_package_name="${package_pre_name}.${install_package_format}.gz"

declare BUILD_DIR="${LOCAL_DIR}/build"
declare MKGS_OK=0
SERVERLIBS_PATH="${serverlib_dir}"
PSYCOPG_VERSION=psycopg2-2.9
declare LOG_FILE="${LOCAL_DIR}/build_psycopg2.log"
declare ERR_MKGS_FAILED=1
echo "[makepython] $(date +%y-%m-%d' '%T): script dir : ${LOCAL_DIR}"

#######################################################################
#  Print log.
#######################################################################
log()
{
    echo "[Build psycopg2] $(date +%y-%m-%d' '%T): $@"
    echo "[Build psycopg2] $(date +%y-%m-%d' '%T): $@" >> "$LOG_FILE" 2>&1
}

#######################################################################
#  print log and exit.
#######################################################################
die()
{
    log "$@"
    echo "$@"
    exit $ERR_MKGS_FAILED
}

# clean build python log
function clean_environment()
{

    if [ -f "$LOG_FILE" ]; then
        rm -rf "$LOG_FILE"
    fi

    if [ -d "${LOCAL_DIR}/build" ]; then
        rm -rf ${LOCAL_DIR}/build
    fi

    echo "clean completely"
}

function check_python()
{
    array=(python3 python2 python)
    for py in ${array[@]}; do
        ${py} -c 'import setuptools' >> /dev/null 2>&1
        if [ $? -eq 0 ]; then
            log "choose python: $(which ${py})"
            PYTHON=${py}
            version=$(${py} --version 2>&1)
            PYTHON_VERSION=python${version:7:1}
            return 0
         fi
    done
    die "the python in your current enviroment is invalid, please check again and install setuptools."
}

function change_gaussdb_version()
{
    if [ ! -f setup.py ]; then
        die "not found psycopg2 code in current working directory."
    fi

    src_text='(pgmajor, pgminor, pgpatch)'
    dst_text='(9, 2, 4)'
    sed -i "s/${src_text}/${dst_text}/g" setup.py
    search_result=$(cat setup.py | grep "$src_text")
    if [ "${search_result}"X != "X" ]; then
        die "failed to replace PG_VERSION_NUM at setup.py."
    fi
}

###############################################################
##  copy the target to set path
###############################################################
function target_file_copy()
{
    cd ${LOCAL_DIR}/build/lib*
    mv psycopg2/_psycopg*.so psycopg2/_psycopg.so

    mkdir -p  lib
    #copy libraries into lib
    cd ./psycopg2
    libs=$(ldd _psycopg.so | awk '{print $3}' | grep $GAUSSHOME/lib)
    for lib in ${libs[@]}; do
        cp $lib ../lib
    done
    cd ..
    
}

#######################################################################
# build and install component
#######################################################################
function build_python()
{
    cd ${LOCAL_DIR}
    # set GAUSSHOME enviroment variable with BUILD_OPTION
    export GAUSSHOME=$SERVERLIBS_PATH
    export LD_LIBRARY_PATH=$GAUSSHOME/lib:$LD_LIBRARY_PATH
    export PATH=${GAUSSHOME}/bin:${PATH}

    echo "GAUSSHOME: ${GAUSSHOME}"

    change_gaussdb_version 
    check_python 
    ${PYTHON} ./setup.py build
    if [ $? -ne 0 ]; then
        die "failed to compile psycopg2."
    fi

    echo "End make python" >> "$LOG_FILE" 2>&1
}

declare package_command
#######################################################################
##select package command accroding to install_package_format
#######################################################################
function select_package_command()
{
    case "$install_package_format" in
        tar)
            tar='tar'
            option=' -zcvf'
            package_command="$tar$option"
            ;;
        rpm)
            rpm='rpm'
            option=' -i'
            package_command="$rpm$option"
            ;;
    esac
}

#######################################################################
##function make_package have tree actions
##1.copy target file into a newly created temporary directory temp
##2.package all file in the temp directory and renome to destination package_path
#######################################################################
function make_package()
{
    target_file_copy
    cd ${BUILD_DIR}/lib*
    select_package_command

    echo "packaging python..."
    $package_command "${python_package_name}" ./lib ./psycopg2 >>"$LOG_FILE" 2>&1
    if [ $? -ne 0 ]; then
        die "$package_command ${python_package_name} failed"
    fi

    mv ${python_package_name} ${BUILD_DIR}/

    echo "install python tools is ${python_package_name} of ${BUILD_DIR} directory " >> "$LOG_FILE" 2>&1
    echo "success!"
}

#############################################################
# main function
#############################################################

# 1. clean environment 
echo "clean enviroment"
echo "[makedb] $(date +%y-%m-%d' '%T): remove ${BUILD_DIR}" >>"$LOG_FILE" 2>&1
clean_environment


# 2. build python
build_python

# 3. make python package
make_package

# 4. cp python package to output
mkdir ${LOCAL_DIR}/output
mv ${BUILD_DIR}/*.tar.gz ${LOCAL_DIR}/output/

echo "now, python driver package has finished!"

exit 0

