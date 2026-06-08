import json
import os
from aws_cdk import (
    Stack,
    Duration,
    RemovalPolicy,
    CfnOutput,
    SecretValue,
    aws_dynamodb as dynamodb,
    aws_lambda as lambda_,
    aws_lambda_event_sources as event_sources,
    aws_iam as iam,
    aws_logs as logs,
    aws_cloudwatch as cw,
    aws_secretsmanager as sm,
    aws_sqs as sqs,
)
from constructs import Construct

LAMBDA_ROOT = os.path.join(os.path.dirname(__file__), "..", "lambdas")


class OdaStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ── Tables ──────────────────────────────────────────────────────────
        # DEMO ONLY — change RemovalPolicy to RETAIN before production
        orders_table = dynamodb.Table(
            self, "OrdersTable",
            table_name="oda-orders",
            partition_key=dynamodb.Attribute(name="order_id", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            stream=dynamodb.StreamViewType.NEW_AND_OLD_IMAGES,
            removal_policy=RemovalPolicy.DESTROY,  # DEMO ONLY — change to RETAIN before production
        )
        orders_table.add_global_secondary_index(
            index_name="customer_id-index",
            partition_key=dynamodb.Attribute(name="customer_id", type=dynamodb.AttributeType.STRING),
        )

        # DEMO ONLY — change RemovalPolicy to RETAIN before production
        action_log_table = dynamodb.Table(
            self, "ActionLogTable",
            table_name="oda-action-log",
            partition_key=dynamodb.Attribute(name="action_id", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="order_id", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,  # DEMO ONLY — change to RETAIN before production
        )

        # ── Dead-Letter Queues ───────────────────────────────────────────────
        decision_dlq = sqs.Queue(
            self, "DecisionDlq",
            queue_name="oda-decision-dlq",
            retention_period=Duration.days(14),
        )
        action_dlq = sqs.Queue(
            self, "ActionDlq",
            queue_name="oda-action-dlq",
            retention_period=Duration.days(14),
        )

        # ── Decision Lambda ──────────────────────────────────────────────────
        decision_log_group = logs.LogGroup(
            self, "DecisionLogGroup",
            log_group_name="/aws/lambda/oda-decision",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=RemovalPolicy.DESTROY,
        )
        decision_fn = lambda_.Function(
            self, "DecisionLambda",
            function_name="oda-decision",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="handler.lambda_handler",
            code=lambda_.Code.from_asset(os.path.join(LAMBDA_ROOT, "decision")),
            environment={
                "ORDERS_TABLE": orders_table.table_name,
                "LOG_LEVEL": "INFO",
                "MODEL_VERSION": "v1.0",
            },
            timeout=Duration.seconds(30),
            memory_size=256,
            log_group=decision_log_group,
            tracing=lambda_.Tracing.ACTIVE,
        )
        orders_table.grant_read_write_data(decision_fn)

        # Trigger: INSERT + MODIFY events on orders table → Decision Lambda
        # Loop prevention is code-level: Decision Lambda skips records where
        # NewImage already contains a 'decision' attribute (set by a prior run).
        decision_fn.add_event_source(
            event_sources.DynamoEventSource(
                orders_table,
                starting_position=lambda_.StartingPosition.LATEST,
                batch_size=10,
                bisect_batch_on_error=True,
                retry_attempts=2,
                on_failure=event_sources.SqsDlq(decision_dlq),
                filters=[
                    lambda_.FilterCriteria.filter({
                        "eventName": lambda_.FilterRule.or_("INSERT", "MODIFY"),
                    })
                ],
            )
        )

        # ── Action Lambda ────────────────────────────────────────────────────
        action_log_group = logs.LogGroup(
            self, "ActionLogGroup",
            log_group_name="/aws/lambda/oda-action",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=RemovalPolicy.DESTROY,
        )
        action_fn = lambda_.Function(
            self, "ActionLambda",
            function_name="oda-action",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="handler.lambda_handler",
            code=lambda_.Code.from_asset(os.path.join(LAMBDA_ROOT, "action")),
            environment={
                "ORDERS_TABLE": orders_table.table_name,
                "ACTION_LOG_TABLE": action_log_table.table_name,
                "LOG_LEVEL": "INFO",
            },
            timeout=Duration.seconds(30),
            memory_size=256,
            log_group=action_log_group,
            tracing=lambda_.Tracing.ACTIVE,
        )
        orders_table.grant_read_write_data(action_fn)
        action_log_table.grant_write_data(action_fn)

        # Trigger: MODIFY events on orders table → Action Lambda
        # Filter: eventName=MODIFY only. Filtering on NewImage attribute existence
        # (e.g. decision exists) silently drops all records in Lambda ESM for DynamoDB
        # streams. Loop prevention is code-level: ConditionExpression on UpdateItem
        # ensures action is only written once per order.
        action_fn.add_event_source(
            event_sources.DynamoEventSource(
                orders_table,
                starting_position=lambda_.StartingPosition.LATEST,
                batch_size=10,
                bisect_batch_on_error=True,
                retry_attempts=2,
                on_failure=event_sources.SqsDlq(action_dlq),
                filters=[
                    lambda_.FilterCriteria.filter({
                        "eventName": lambda_.FilterRule.is_equal("MODIFY"),
                    })
                ],
            )
        )

        # ── IAM Evaluator User ───────────────────────────────────────────────
        evaluator = iam.User(self, "EvaluatorUser", user_name="oda-evaluator")
        for policy_name in [
            "AmazonDynamoDBReadOnlyAccess",
            "AWSLambda_ReadOnlyAccess",
            "CloudWatchReadOnlyAccess",
        ]:
            evaluator.add_managed_policy(
                iam.ManagedPolicy.from_aws_managed_policy_name(policy_name)
            )

        evaluator_key = iam.CfnAccessKey(
            self, "EvaluatorAccessKey",
            user_name=evaluator.user_name,
        )

        sm.Secret(
            self, "EvaluatorCredentials",
            secret_name="oda-evaluator-credentials",
            secret_string_value=SecretValue.unsafe_plain_text(
                json.dumps({
                    "access_key_id": evaluator_key.ref,
                    "secret_access_key": evaluator_key.attr_secret_access_key,
                    "region": self.region,
                    "note": "Read-only evaluator access for ODA case study review",
                })
            ),
        )

        # ── CloudWatch Dashboard ─────────────────────────────────────────────
        dashboard = cw.Dashboard(self, "OdaDashboard", dashboard_name="ODA-Pipeline")

        def _lambda_metric(fn: lambda_.Function, metric_name: str, statistic: str = "Sum") -> cw.Metric:
            return cw.Metric(
                namespace="AWS/Lambda",
                metric_name=metric_name,
                dimensions_map={"FunctionName": fn.function_name},
                period=Duration.minutes(5),
                statistic=statistic,
            )

        dashboard.add_widgets(
            cw.GraphWidget(
                title="Lambda Invocations",
                left=[
                    _lambda_metric(decision_fn, "Invocations"),
                    _lambda_metric(action_fn,   "Invocations"),
                ],
                width=12,
            ),
            cw.GraphWidget(
                title="Lambda Errors",
                left=[
                    _lambda_metric(decision_fn, "Errors"),
                    _lambda_metric(action_fn,   "Errors"),
                ],
                width=12,
            ),
            cw.GraphWidget(
                title="Stream IteratorAge (ms) — p99",
                left=[
                    _lambda_metric(decision_fn, "IteratorAge", "p99"),
                    _lambda_metric(action_fn,   "IteratorAge", "p99"),
                ],
                width=12,
            ),
            cw.GraphWidget(
                title="Lambda Duration (ms) — p99",
                left=[
                    _lambda_metric(decision_fn, "Duration", "p99"),
                    _lambda_metric(action_fn,   "Duration", "p99"),
                ],
                width=12,
            ),
            cw.LogQueryWidget(
                title="Decision Distribution (AUTO_APPROVE / MANUAL_REVIEW / DECLINE)",
                log_group_names=["/aws/lambda/oda-decision"],
                query_lines=[
                    'filter event = "decision_made"',
                    'stats count(*) as orders by outcome',
                    'sort orders desc',
                ],
                view=cw.LogQueryVisualizationType.PIE,
                width=12,
                height=6,
            ),
            cw.LogQueryWidget(
                title="Action Distribution (FULFILLED / ESCALATED / REJECTED)",
                log_group_names=["/aws/lambda/oda-action"],
                query_lines=[
                    'filter event = "action_taken"',
                    'stats count(*) as orders by action',
                    'sort orders desc',
                ],
                view=cw.LogQueryVisualizationType.PIE,
                width=12,
                height=6,
            ),
        )

        # ── Outputs ──────────────────────────────────────────────────────────
        CfnOutput(self, "OrdersTableName", value=orders_table.table_name)
        CfnOutput(self, "ActionLogTableName", value=action_log_table.table_name)
        CfnOutput(self, "DecisionLambdaArn", value=decision_fn.function_arn)
        CfnOutput(self, "ActionLambdaArn", value=action_fn.function_arn)
        CfnOutput(self, "DecisionDlqUrl", value=decision_dlq.queue_url)
        CfnOutput(self, "ActionDlqUrl", value=action_dlq.queue_url)
        CfnOutput(self, "EvaluatorSecretArn",
                  value=f"arn:aws:secretsmanager:{self.region}:{self.account}:secret:oda-evaluator-credentials")
        CfnOutput(self, "DashboardUrl",
                  value=f"https://{self.region}.console.aws.amazon.com/cloudwatch/home#dashboards:name=ODA-Pipeline")
