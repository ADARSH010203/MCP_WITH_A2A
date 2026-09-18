from app.routing.planner import CollaborationPlanner


TASK_FOCUS = {
    "deep_learning": "Design the model and training pipeline.",
    "code": "Implement the solution.",
    "game": "Design the game mechanics.",
    "reinforcement": "Design the reinforcement-learning approach.",
}


HANDOFF_TARGETS = {
    "code": ("deep_learning", "reinforcement", "game"),
}


def test_single_agent_plan_has_one_step():
    plan = CollaborationPlanner().build(
        query="Explain CNNs",
        agent_types=["deep_learning"],
        task_focus=TASK_FOCUS,
        handoff_targets=HANDOFF_TARGETS,
    )

    assert plan.mode == "single-agent"
    assert plan.agents == ("deep_learning",)
    assert len(plan.steps) == 1
    assert plan.steps[0].agent == "deep_learning"
    assert plan.handoffs == {}


def test_multi_agent_plan_parallelizes_independent_work():
    plan = CollaborationPlanner().build(
        query="Build a Python CNN pipeline",
        agent_types=["deep_learning", "code"],
        task_focus=TASK_FOCUS,
        handoff_targets=HANDOFF_TARGETS,
    )

    assert plan.mode == "multi-agent"
    assert plan.handoffs == {"code": ("deep_learning",)}

    lead = next(step for step in plan.steps if step.agent == "deep_learning")
    code = next(step for step in plan.steps if step.agent == "code")
    critic = next(step for step in plan.steps if step.agent == "critic")

    assert lead.parallel_group == 1
    assert lead.depends_on == ()
    assert code.parallel_group == 2
    assert code.depends_on == ("deep_learning",)
    assert critic.parallel_group == 3
    assert set(critic.depends_on) == {"deep_learning", "code"}


def test_plan_is_serializable_for_a2a_metadata():
    plan = CollaborationPlanner().build(
        query="Design a game using Q-learning and implement it",
        agent_types=["game", "reinforcement", "code"],
        task_focus=TASK_FOCUS,
        handoff_targets=HANDOFF_TARGETS,
    )

    payload = plan.to_dict()

    assert payload["mode"] == "multi-agent"
    assert payload["agents"] == ["game", "reinforcement", "code"]
    assert payload["handoffs"]["code"] == ["reinforcement", "game"]
    assert payload["steps"][-1]["agent"] == "critic"
