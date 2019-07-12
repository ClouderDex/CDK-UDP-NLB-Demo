import setuptools


with open("README.md") as fp:
    long_description = fp.read()


setuptools.setup(
    name="cdk_udp_nlb_demo",
    version="0.0.1",

    description="A demo CDK app using an UDP NLB logging with td-agent to S3",
    long_description=long_description,
    long_description_content_type="text/markdown",

    author="Dexter Markley - @ClouderDex",

    package_dir={"": "cdk_udp_nlb_demo"},
    packages=setuptools.find_packages(where="cdk_udp_nlb_demo"),

    install_requires=[
        "aws-cdk.core",
        "aws-cdk.aws-ec2",
        "aws-cdk.aws-iam",
        "aws-cdk.aws-s3",
        "aws-cdk.aws-autoscaling",
        "aws-cdk.aws-elasticloadbalancingv2",
    ],

    python_requires=">=3.6",
)
