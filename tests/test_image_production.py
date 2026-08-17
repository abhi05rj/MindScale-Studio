import subprocess
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from app.image_engine import (
    CoreMLStableDiffusionProvider,
    FakeImageProvider,
    ImageGenerationRequest,
    PinterestCompositionRequest,
    PinterestImageCompositor,
    PinterestImageValidator,
    PillowTemplateProvider,
)


class ImageProductionTests(unittest.TestCase):
    def test_fake_provider_and_compositor_create_valid_pinterest_asset(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            background_path = root / "background.png"
            final_path = root / "pin.png"

            generated = FakeImageProvider().generate(
                ImageGenerationRequest(
                    prompt="Abstract cosmic scale, no text",
                    output_path=background_path,
                    seed=42,
                )
            )
            result = PinterestImageCompositor().compose(
                PinterestCompositionRequest(
                    background_path=generated.output_path,
                    title="How Small Are Humans Compared to the Universe?",
                    output_path=final_path,
                )
            )

            self.assertEqual((result.width, result.height), (1000, 1500))
            self.assertEqual(result.image_format, "PNG")
            self.assertEqual(PinterestImageValidator().validate(final_path), result)

            with Image.open(final_path) as image:
                self.assertEqual(image.mode, "RGB")

    def test_fake_provider_is_deterministic_for_the_same_seed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "first.png"
            second = root / "second.png"
            provider = FakeImageProvider()
            common = {"prompt": "background only", "seed": 7}

            provider.generate(ImageGenerationRequest(output_path=first, **common))
            provider.generate(ImageGenerationRequest(output_path=second, **common))

            self.assertEqual(first.read_bytes(), second.read_bytes())

    def test_coreml_provider_is_replaceable_and_invokes_external_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            model_directory = root / "model"
            model_directory.mkdir()
            executable = root / "python"
            executable.touch()
            destination = root / "background.png"
            observed_command = []

            def fake_command_runner(command, **kwargs):
                observed_command.extend(command)
                output_directory = Path(command[command.index("-o") + 1])
                Image.new("RGB", (512, 512), "navy").save(output_directory / "result.png")
                return subprocess.CompletedProcess(command, 0)

            provider = CoreMLStableDiffusionProvider(
                model_directory=model_directory,
                python_executable=executable,
                command_runner=fake_command_runner,
            )
            result = provider.generate(
                ImageGenerationRequest(
                    prompt="A local visual background, no text",
                    output_path=destination,
                    seed=99,
                    inference_steps=18,
                )
            )

            self.assertTrue(destination.is_file())
            self.assertEqual(result.provider, "CoreMLStableDiffusionProvider")
            self.assertIn("app.image_engine.coreml_runner", observed_command)
            self.assertIn("99", observed_command)
            self.assertIn("18", observed_command)

    def test_validator_rejects_wrong_dimensions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "wrong-size.png"
            Image.new("RGB", (512, 512)).save(path)

            with self.assertRaisesRegex(ValueError, "must be 1000x1500"):
                PinterestImageValidator().validate(path)

    def test_production_templates_are_topic_aware_and_include_three_variants(self):
        provider = PillowTemplateProvider()
        self.assertEqual(provider.select_template("cosmic universe scale"), "cosmic_orbits")
        self.assertEqual(provider.select_template("nature and ocean"), "organic_layers")
        self.assertEqual(provider.select_template("human brain network"), "connected_minds")

    def test_production_template_is_deterministic_and_full_size(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "first.png"
            second = root / "second.png"
            provider = PillowTemplateProvider()
            request_values = {
                "prompt": "A visual journey through nature",
                "width": 1000,
                "height": 1500,
                "seed": 42,
                "inference_steps": 1,
            }
            result = provider.generate(ImageGenerationRequest(output_path=first, **request_values))
            provider.generate(ImageGenerationRequest(output_path=second, **request_values))

            self.assertEqual((result.width, result.height), (1000, 1500))
            self.assertEqual(result.model, "pillow-organic_layers-v1")
            self.assertEqual(first.read_bytes(), second.read_bytes())


if __name__ == "__main__":
    unittest.main()
