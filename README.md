# openGauss-connector-python-psycopg2

## 介绍

该仓库为openGauss的python驱动。

## 打包步骤

1. 推荐使用python3，请在服务器上装python3和python3-devel

    ```shell
    yum install python3 python3-devel
    ```

2. python驱动的打包需要依赖openGauss-server编译的libpq，请参照 [openGauss使用命令编译代码](https://gitee.com/opengauss/openGauss-server#%E4%BD%BF%E7%94%A8%E5%91%BD%E4%BB%A4%E7%BC%96%E8%AF%91%E4%BB%A3%E7%A0%81)

3. 下载 `openGauss-connector-python-psycopg2` 仓库代码，进入到根目录下，执行

    ```shell
    sh build.sh -bd /data/compile/openGauss-server/dest/ -v 5.0.0
    ```

    **说明** \
    -bd: 指定openGauss数据库构建结果目录 \
    -v: 指定构建包的版本号。不指定则默认为5.0.0

    编译完成后的驱动，在 `output` 目录下。

## 软件下载

社区每日构建，提供三套环境已经编译好的驱动包供使用，下载路径如下：

其中 **\<VERSION\>** 为当前最新的版本号。

openEuler-aarch64:

`https://opengauss.obs.cn-south-1.myhuaweicloud.com/latest/arm/openGauss-<VERSION>-openEuler-aarch64-Python.tar.gz`

CentOS-x86_64:

`https://opengauss.obs.cn-south-1.myhuaweicloud.com/latest/x86/openGauss-<VERSION>-CentOS-x86_64-Python.tar.gz`

openEuler-x86_64:

`https://opengauss.obs.cn-south-1.myhuaweicloud.com/latest/x86_openEuler/openGauss-<VERSION>-openEuler-x86_64-Python.tar.gz`

## 使用说明

### 安装 psycopg2

解压安装包后，会得到两个目录 `lib` 和 `psycopg2`。

接下来您需要将 psycopg2 目录拷贝到 Python 解释器的 site-packages 下，让 python 可以索引到

可以通过如下指令来查找 site-packages 目录所在位置:

```shell
python -c "from distutils.sysconfig import get_python_lib;print(get_python_lib())"
# output: /usr/lib/python3.6/site-packages
```

确定 site-packages 的目录位置后，将 psycopg2 文件夹整个拷贝该目录下，并授权便于其他用户使用

```shell
cp -r psycopg2 [/path/to/site-packages/] && chmod 755 [/path/to/site-packages/]psycopg2
```

安装包中的另一个目录 `lib` 是 psycopg2 依赖的 libpq 等 C 动态库文件。

这个目录中的文件可能会和系统的动态库存在重名冲突的问题，

所以建议将应用程序和 lib 目录存放到单独的一个系统用户下和系统自带库进行隔离，避免影响系统其他工具。

切换到运行用户下，执行如下命令进行设置：

```shell
echo "export LD_LIBRARY_PATH=[/path/to/lib]:$LD_LIBRARY_PATH" >> ~/.bashrc
source ~/.bashrc
```

这样就安装完成了。

### 应用连接

```python
import psycopg2

# dsn 格式
conn = psycopg2.connect("postgres://user:password@ip1:port,ip2:port:.../dbname?target_session_attrs=[any|read-write]")
# key-value 格式
conn = psycopg2.connect(host="ip1[,ip2]",
                        port=port1,
                        database=db,
                        user=user,
                        password=password,
                        target_session_attrs="read-write")
```

## 参与贡献

1. Fork 本仓库
2. 新建 Feat_xxx 分支
3. 提交代码
4. 新建 Pull Request
