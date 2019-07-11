#!/usr/bin/env python3

from aws_cdk import core

from cdk_udp_nlb_demo.cdk_udp_nlb_demo_stack import CdkUdpNlbDemoStack


app = core.App()
CdkUdpNlbDemoStack(app, "cdk-udp-nlb-demo-cdk-1")

app.synth()
