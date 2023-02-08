# openGauss-connector-python-psycopg2

#### 介绍

该仓库为openGauss的python驱动。

#### 软件架构


#### 打包步骤

1. 推荐使用python3，请在服务器上装python3和python3-devel
```
yum install python3 python3-devel
```

2. python驱动的打包需要依赖openGauss-server编译的libpq，请参照 [openGauss使用命令编译代码](https://gitee.com/opengauss/openGauss-server#%E4%BD%BF%E7%94%A8%E5%91%BD%E4%BB%A4%E7%BC%96%E8%AF%91%E4%BB%A3%E7%A0%81) 

3. 下载`openGauss-connector-python-psycopg2`仓库代码，进入到根目录下，执行
```
sh build.sh -bd /data/compile/openGauss-server/dest/ -v 5.0.0
```
**说明** \
-bd: 指定openGauss数据库构建结果目录 \
-v: 指定构建包的版本号。不指定则默认为5.0.0

编译完成后的驱动，在 `output` 目录下。

#### 软件下载

社区每日构建，提供三套环境已经编译好的驱动包供使用，下载路径如下：

其中 **VERSION** 为当前最新的版本号。

openEuler-aarch64：\
https://opengauss.obs.cn-south-1.myhuaweicloud.com/latest/arm/openGauss-**VERSION**-openEuler-aarch64-Python.tar.gz


CentOS-x86_64: \
https://opengauss.obs.cn-south-1.myhuaweicloud.com/latest/x86/openGauss-**VERSION**-CentOS-x86_64-Python.tar.gz


openEuler-x86_64: \
https://opengauss.obs.cn-south-1.myhuaweicloud.com/latest/x86_openEuler/openGauss-**VERSION**-openEuler-x86_64-Python.tar.gz


#### 使用说明

1.  xxxx
2.  xxxx
3.  xxxx

#### 参与贡献

1.  Fork 本仓库
2.  新建 Feat_xxx 分支
3.  提交代码
4.  新建 Pull Request


#### 特技

1.  使用 Readme\_XXX.md 来支持不同的语言，例如 Readme\_en.md, Readme\_zh.md
2.  Gitee 官方博客 [blog.gitee.com](https://blog.gitee.com)
3.  你可以 [https://gitee.com/explore](https://gitee.com/explore) 这个地址来了解 Gitee 上的优秀开源项目
4.  [GVP](https://gitee.com/gvp) 全称是 Gitee 最有价值开源项目，是综合评定出的优秀开源项目
5.  Gitee 官方提供的使用手册 [https://gitee.com/help](https://gitee.com/help)
6.  Gitee 封面人物是一档用来展示 Gitee 会员风采的栏目 [https://gitee.com/gitee-stars/](https://gitee.com/gitee-stars/)
