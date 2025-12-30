"""Base classes for pipeline stages."""

from abc import ABC, abstractmethod
import time

from music_tutor.models.pipeline import ProcessingContext, StageResult


class PipelineStage(ABC):
    """Abstract base class for pipeline stages.

    Each stage implements execute() which receives a ProcessingContext,
    performs its work (mutating the context), and returns a StageResult.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique name for this stage."""
        ...

    @abstractmethod
    def execute(self, context: ProcessingContext) -> StageResult:
        """Execute this stage.

        Args:
            context: Mutable processing context that accumulates results.

        Returns:
            StageResult indicating success/failure and any warnings.
        """
        ...

    def run(self, context: ProcessingContext) -> StageResult:
        """Run the stage with timing.

        This is the public entry point that wraps execute() with timing
        and error handling.
        """
        start_time = time.time()
        try:
            result = self.execute(context)
            result.duration_seconds = time.time() - start_time
            return result
        except Exception as e:
            return StageResult(
                success=False,
                stage_name=self.name,
                duration_seconds=time.time() - start_time,
                error_message=f"Unexpected error: {e}",
            )
