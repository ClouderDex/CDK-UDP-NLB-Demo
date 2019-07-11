from aws_cdk import (
    core,
    aws_autoscaling as autoscaling,
    aws_ec2 as ec2,
    aws_iam as iam,
    aws_elasticloadbalancingv2 as elbv2,
    aws_s3 as s3,
)

# TODO - Change these settings to match your requirements
PUBLIC_ACCESS = False  # True to use public NLB and Instances. If NLB is in Public, instances must be public as well.
NLB_ACCESS_IPV4 = "127.0.0.1/32"  # Change this to your public IP for NLB access if you set PUBLIC_ACCESS true
UDP_LISTEN_PORT = 5160


def install_td_agent_user_data(asg, udp_logs_bucket, udp_listen_port):
    """
    Adds userdata to an autoscaling group to install the td-agent
    :param asg: The ASG which should include user data for installing td-agent
    :param udp_logs_bucket: The s3 resource where udp logs should land
    :param udp_listen_port: The udp listen port for the NLB and Instances
    :return: NA
    """
    user_data = [
        "curl -L https://toolbelt.treasuredata.com/sh/install-amazon1-td-agent3.sh | sh",
        "cat <<EOF > /etc/td-agent/td-agent.conf",
        open("cdk_udp_nlb_demo/td-agent.conf", "r").read(),
        "EOF",
        "instance_id=$(curl http://169.254.169.254/latest/meta-data/instance-id)",
        'sudo sed -i "s/instance-id/${!instance_id}/g" /etc/td-agent/td-agent.conf',
        "sudo service td-agent restart",
    ]
    variables = {"UdpBucket": udp_logs_bucket.bucket_name, "UdpListenPort": str(udp_listen_port)}

    asg.add_user_data(core.Fn.sub("\n".join(user_data), variables=variables))


class CdkUdpNlbDemoStack(core.Stack):
    def __init__(self, app: core.App, id: str, **kwargs) -> None:
        super().__init__(app, id, **kwargs)

        # Create an S3 bucket where we will store the UDP logs
        udp_logs_bucket = s3.Bucket(self, "UDPLogsBucket")

        # Create a VPC using CDK's default VPC architecture. See README for diagram.
        vpc = ec2.Vpc(self, "VPC")

        workers_asg = autoscaling.AutoScalingGroup(
            self,
            "ASG",
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PUBLIC if PUBLIC_ACCESS else ec2.SubnetType.PRIVATE
            ),
            instance_type=ec2.InstanceType("t2.small"),
            machine_image=ec2.AmazonLinuxImage(),
            desired_capacity=1 if PUBLIC_ACCESS else 2
        )

        # Create a security group that controls access to the NLB > Instances
        # It is important to note that NLB security works different than Classic ELB or ALB
        # NLBs do not attach security groups, security controls are managed on the instances themselves!
        allow_udp_sg = ec2.SecurityGroup(
            self,
            "AllowUdpSG",
            vpc=vpc,
            description="Allow UDP listener through Network Load Balancer",
            allow_all_outbound=False,  # The default SG for the ASG is already allowing all outbound
        )

        # Add rules to the security group for internal access, and the configured NLB_PUBLIC_ACCESS
        for ipv4 in [NLB_ACCESS_IPV4, vpc.vpc_cidr_block]:
            allow_udp_sg.add_ingress_rule(
                peer=ec2.Peer.ipv4(ipv4),
                connection=ec2.Port(
                    string_representation=str(UDP_LISTEN_PORT),
                    protocol=ec2.Protocol.UDP,
                    from_port=UDP_LISTEN_PORT,
                    to_port=UDP_LISTEN_PORT,
                ),
            )
        workers_asg.add_security_group(allow_udp_sg)

        # Add the td-agent to our worker instances using user-data scripts
        # Example of using an external function to modify a resource
        install_td_agent_user_data(workers_asg, udp_logs_bucket, UDP_LISTEN_PORT)

        # Attach the SSM Managed policy for managing the instance through SSM Sessions
        # This allows us to ditch bastions hosts!
        # This policy also is granting us S3 access for logging, if you remove it you will need to add an IAM role
        # with access to the s3 bucket.
        managed_policy = iam.ManagedPolicy().from_aws_managed_policy_name(
            managed_policy_name="service-role/AmazonEC2RoleforSSM"
        )
        workers_asg.role.add_managed_policy(managed_policy)

        # Create a network load balancer for accepting our UDP logs
        # This will create the required EIPs when configured for Public Access
        lb = elbv2.NetworkLoadBalancer(self, "LB", vpc=vpc, cross_zone_enabled=True, internet_facing=PUBLIC_ACCESS)

        # Create a listener & target group for our NLB.
        # It is important to note that the TCP protocol will be overriden to UDP shortly
        listener = lb.add_listener("Listener", port=UDP_LISTEN_PORT, protocol=elbv2.Protocol.TCP)
        target_group = elbv2.NetworkTargetGroup(self, vpc=vpc, id="Target", port=UDP_LISTEN_PORT, targets=[workers_asg])
        listener.add_target_groups("TargetGroupUdp", target_group)

        # Workaround for lack of UDP NLB support in CDK.
        # As of writing this CDK does not have support for UDP NLBs
        # TODO - Remove these overrides when support is added
        # https://github.com/awslabs/aws-cdk/issues/3107
        listener.node.find_child("Resource").add_property_override("Protocol", "UDP")
        target_group.node.find_child("Resource").add_property_override("Protocol", "UDP")
