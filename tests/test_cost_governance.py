from app.observability.cost import CostBudget, CostPolicy, TokenUsage


def test_token_usage_extracts_langchain_usage_metadata():
    class Message:
        usage_metadata = {
            "input_tokens": 120,
            "output_tokens": 80,
            "total_tokens": 200,
        }

    usage = TokenUsage.from_message(Message())

    assert usage is not None
    assert usage.input_tokens == 120
    assert usage.output_tokens == 80
    assert usage.total_tokens == 200


def test_token_usage_supports_legacy_token_usage_shape():
    class Message:
        usage_metadata = None
        response_metadata = {
            "token_usage": {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
            }
        }

    usage = TokenUsage.from_message(Message())

    assert usage is not None
    assert usage.to_dict() == {
        "input_tokens": 10,
        "output_tokens": 5,
        "total_tokens": 15,
    }


def test_cost_policy_estimates_without_hardcoding_provider_prices():
    policy = CostPolicy(
        input_usd_per_1m_tokens=2.0,
        output_usd_per_1m_tokens=6.0,
    )
    usage = TokenUsage(input_tokens=1000, output_tokens=500)

    assert policy.estimate(usage) == 0.005


def test_cost_budget_stops_after_token_limit():
    budget = CostBudget(
        CostPolicy(
            max_total_tokens_per_task=100,
            input_usd_per_1m_tokens=1.0,
            output_usd_per_1m_tokens=1.0,
        )
    )

    assert budget.record(
        TokenUsage(input_tokens=40, output_tokens=40),
        agent="code",
        execution_mode="local",
    ) is True
    assert budget.record(
        TokenUsage(input_tokens=20, output_tokens=20),
        agent="critic",
        execution_mode="local",
    ) is False

    snapshot = budget.snapshot()
    assert snapshot["total_tokens"] == 120
    assert snapshot["budget_exceeded"] is True


def test_cost_budget_stops_after_usd_limit():
    budget = CostBudget(
        CostPolicy(
            input_usd_per_1m_tokens=10.0,
            output_usd_per_1m_tokens=10.0,
            max_estimated_cost_usd_per_task=0.0005,
        )
    )

    assert budget.record(
        TokenUsage(input_tokens=50, output_tokens=20),
        agent="email",
        execution_mode="local",
    ) is False
    assert budget.snapshot()["budget_exceeded"] is True


def test_zero_usage_is_explicitly_tolerated_for_unknown_provider_usage():
    budget = CostBudget(CostPolicy(max_total_tokens_per_task=100))

    assert budget.record(
        None,
        agent="remote",
        execution_mode="remote-a2a",
    ) is True
    assert budget.snapshot()["total_tokens"] == 0
