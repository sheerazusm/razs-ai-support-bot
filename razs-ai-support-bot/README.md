# Raz's AI customer support bot

A serverless AWS support bot for a fictional cloud storage product ("Raz's AI"),
built to demonstrate applying Amazon Bedrock inside a real production-shaped
pipeline rather than calling an AI API directly from a frontend.

## Architecture

```
Client -> API Gateway -> Orchestrator Lambda -> DynamoDB (conversation history)
                                              -> Amazon Bedrock (generates reply)
                                              -> Validator Lambda (business rules, escalation)
                       <- Reply
CloudWatch + SNS monitor the orchestrator (errors, p95 latency) and email on threshold breach.
```

- **API Gateway** exposes a single `POST /chat` endpoint.
- **Orchestrator Lambda** loads the last few turns of conversation from
  DynamoDB, builds a prompt (system rules + history + new message), and
  calls Bedrock via the `converse` API.
- **DynamoDB** stores conversation history per `session_id`, with a 7-day
  TTL so old sessions clean themselves up.
- **Validator Lambda** is invoked synchronously by the orchestrator. It
  checks the customer's message for topics the bot should never answer on
  its own (refunds, security, data loss) and forces a human handoff for
  those, regardless of what Bedrock generated.
- **CloudWatch alarms** watch Lambda error count and p95 duration; both
  publish to an **SNS topic** that emails an alert.

Business rules and the bot's persona live in `src/shared/python/business_context.py`,
packaged as a Lambda layer so both functions share it instead of duplicating
logic.

## Deploy

Requires the [AWS SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/serverless-sam-cli-install.html)
and an AWS account with Bedrock model access enabled for the model in
`template.yaml` (`anthropic.claude-3-5-haiku-20241022-v1:0` by default).

```bash
sam build
sam deploy --guided
```

`sam deploy --guided` will prompt for the `AlertEmail` parameter and confirm
IAM changes. After deploy, grab the `ChatEndpoint` value from the outputs and
paste it into `frontend/index.html` (`API_ENDPOINT`), then open that file in
a browser to try it.

## Why it's built this way

- **Two Lambdas, not one.** The orchestrator's job is "generate a good
  answer." The validator's job is "make sure the bot doesn't say something
  the business can't stand behind." Splitting them means the escalation
  rules can be tested and changed without touching prompt logic, and
  they can scale/fail independently.
- **DynamoDB with TTL**, not a database with manual cleanup, since chat
  history is naturally short-lived and disposable.
- **CloudWatch + SNS from day one**, because "it works in the demo" and
  "it's production-ready" are different bars, and monitoring is the gap
  most portfolio projects skip.

## What's a fictional stand-in

Raz's AI, its pricing, and its support policies are entirely made up for
this project. This is intentionally decoupled from any real business.
