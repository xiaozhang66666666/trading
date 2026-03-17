import unittest

from app.core.models import StrategyDirectionConfig, StrategyPayload, StrategyTemplate
from app.services.strategy_service import StrategyService, StrategyValidationError


def _payload(json_dsl: str) -> StrategyPayload:
    return StrategyPayload(
        name="策略A",
        template=StrategyTemplate.MA_CROSS,
        interval="15m",
        open_condition="MA5 上穿 MA20",
        close_condition="MA5 下穿 MA20",
        take_profit=3.0,
        stop_loss=1.2,
        position_size=0.3,
        direction=StrategyDirectionConfig(allow_long=True, allow_short=True, include_extended_hours=False),
        json_dsl=json_dsl,
    )


class StrategyServiceTest(unittest.TestCase):
    def test_create_and_copy_strategy(self) -> None:
        service = StrategyService()
        strategy = service.create(
            _payload(
                '{"strategy":{},"indicators":[],"conditions":{},"entry_long":{},"exit_long":{},"entry_short":{},"exit_short":{},"risk":{}}'
            )
        )
        self.assertEqual(strategy.current_version, 1)

        copied = service.copy(strategy.id)
        self.assertIn("副本", copied.name)

    def test_invalid_json_should_raise(self) -> None:
        service = StrategyService()
        with self.assertRaises(StrategyValidationError):
            service.create(_payload("{invalid json}"))


if __name__ == "__main__":
    unittest.main()
