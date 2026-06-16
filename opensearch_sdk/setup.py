from setuptools import setup, find_packages

setup(
    name="opensearch_sdk",
    version="0.1.0",
    description="Opensearch兼容接口compatible with OpenSearch syntax",
    author="Your Name",
    author_email="your.email@example.com",
    packages=find_packages(),
    install_requires=[
        "psycopg2-binary>=2.8.0",
        "typing_extensions>=3.7.4; python_version<'3.8'",
    ],
    python_requires=">=3.6",
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: Apache Software License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
    ],
    include_package_data=True,
)