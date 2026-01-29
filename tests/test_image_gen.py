"""Tests for image_gen.py module."""
import base64
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestIsImageGenerationEnabled:
    """Tests for is_image_generation_enabled function."""

    def test_returns_false_when_no_key(self):
        """Should return False when OPENROUTER_API_KEY is not set."""
        with patch.dict(os.environ, {}, clear=True):
            # Need to reimport to pick up the new environment
            import importlib
            import image_gen
            importlib.reload(image_gen)
            assert image_gen.is_image_generation_enabled() is False

    def test_returns_true_when_key_set(self):
        """Should return True when OPENROUTER_API_KEY is set."""
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}, clear=True):
            import importlib
            import image_gen
            importlib.reload(image_gen)
            assert image_gen.is_image_generation_enabled() is True

    def test_returns_false_for_empty_key(self):
        """Should return False when OPENROUTER_API_KEY is empty string."""
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": ""}, clear=True):
            import importlib
            import image_gen
            importlib.reload(image_gen)
            assert image_gen.is_image_generation_enabled() is False


class TestGetFluxModel:
    """Tests for get_flux_model function."""

    def test_returns_default_when_not_set(self):
        """Should return default model when FLUX_MODEL is not set."""
        with patch.dict(os.environ, {}, clear=True):
            import importlib
            import image_gen
            importlib.reload(image_gen)
            assert image_gen.get_flux_model() == "black-forest-labs/flux.2-klein-4b"

    def test_returns_env_value_when_set(self):
        """Should return env value when FLUX_MODEL is set."""
        with patch.dict(os.environ, {"FLUX_MODEL": "black-forest-labs/flux.2-max"}, clear=True):
            import importlib
            import image_gen
            importlib.reload(image_gen)
            assert image_gen.get_flux_model() == "black-forest-labs/flux.2-max"


class TestGenerateCoverPrompt:
    """Tests for generate_cover_prompt function."""

    def test_includes_title(self):
        """Prompt should include the novel title."""
        from image_gen import generate_cover_prompt
        prompt = generate_cover_prompt("My Novel Title", "A story concept")
        assert "My Novel Title" in prompt

    def test_includes_concept(self):
        """Prompt should include the story concept."""
        from image_gen import generate_cover_prompt
        prompt = generate_cover_prompt("Title", "A thrilling adventure story")
        assert "thrilling adventure" in prompt

    def test_truncates_long_concept(self):
        """Prompt should truncate very long concepts."""
        from image_gen import generate_cover_prompt
        long_concept = "x" * 1000
        prompt = generate_cover_prompt("Title", long_concept)
        # Should be truncated to 800 chars
        assert len(long_concept) > 800
        assert "x" * 800 in prompt
        assert "x" * 801 not in prompt

    def test_includes_no_text_requirement(self):
        """Prompt should specify no text on image."""
        from image_gen import generate_cover_prompt
        prompt = generate_cover_prompt("Title", "Concept")
        assert "NO text" in prompt.lower() or "no text" in prompt.lower()


class TestGenerateChapterPrompt:
    """Tests for generate_chapter_prompt function."""

    def test_includes_novel_title(self):
        """Prompt should include the novel title."""
        from image_gen import generate_chapter_prompt
        prompt = generate_chapter_prompt("My Novel", "Chapter One", "Scene content")
        assert "My Novel" in prompt

    def test_includes_chapter_title(self):
        """Prompt should include the chapter title."""
        from image_gen import generate_chapter_prompt
        prompt = generate_chapter_prompt("Novel", "The Great Escape", "Content")
        assert "The Great Escape" in prompt

    def test_includes_excerpt(self):
        """Prompt should include scene excerpt."""
        from image_gen import generate_chapter_prompt
        prompt = generate_chapter_prompt("Novel", "Chapter", "The hero stood on the cliff")
        assert "hero stood on the cliff" in prompt

    def test_truncates_long_excerpt(self):
        """Prompt should truncate very long excerpts."""
        from image_gen import generate_chapter_prompt
        long_excerpt = "y" * 800
        prompt = generate_chapter_prompt("Novel", "Chapter", long_excerpt)
        # Should be truncated to 600 chars
        assert "y" * 600 in prompt
        assert "y" * 601 not in prompt


class TestSaveImage:
    """Tests for save_image function."""

    def test_creates_parent_directories(self, tmp_path):
        """Should create parent directories if they don't exist."""
        from image_gen import save_image
        nested_path = tmp_path / "a" / "b" / "c" / "image.png"
        image_bytes = b"fake image data"

        save_image(image_bytes, nested_path)

        assert nested_path.exists()
        assert nested_path.read_bytes() == image_bytes

    def test_overwrites_existing_file(self, tmp_path):
        """Should overwrite existing file."""
        from image_gen import save_image
        path = tmp_path / "image.png"
        path.write_bytes(b"old data")

        save_image(b"new data", path)

        assert path.read_bytes() == b"new data"


class TestGenerateImage:
    """Tests for generate_image function with mocked API."""

    def test_raises_without_api_key(self):
        """Should raise ValueError when API key not set."""
        # Test that get_openrouter_client raises ValueError without API key
        with patch.dict(os.environ, {}, clear=True):
            import importlib
            import image_gen
            importlib.reload(image_gen)

            with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
                image_gen.get_openrouter_client()

    @patch("image_gen.get_openrouter_client")
    def test_returns_image_bytes_from_data_url(self, mock_get_client):
        """Should parse base64 data URL and return image bytes."""
        # Create mock response with base64 image
        test_image_data = b"PNG image data here"
        b64_data = base64.b64encode(test_image_data).decode()

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = f"data:image/png;base64,{b64_data}"
        mock_response.choices[0].message.images = None
        mock_client.chat.completions.create.return_value = mock_response
        mock_get_client.return_value = mock_client

        from image_gen import generate_image
        image_bytes, ext = generate_image("test prompt")

        assert image_bytes == test_image_data
        assert ext == "png"

    @patch("image_gen.get_openrouter_client")
    def test_returns_correct_extension_for_jpeg(self, mock_get_client):
        """Should return correct extension for JPEG images."""
        test_image_data = b"JPEG image data"
        b64_data = base64.b64encode(test_image_data).decode()

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = f"data:image/jpeg;base64,{b64_data}"
        mock_response.choices[0].message.images = None
        mock_client.chat.completions.create.return_value = mock_response
        mock_get_client.return_value = mock_client

        from image_gen import generate_image
        image_bytes, ext = generate_image("test prompt")

        assert ext == "jpeg"

    @patch("image_gen.get_openrouter_client")
    def test_uses_custom_model(self, mock_get_client):
        """Should use custom model when specified."""
        test_image_data = b"image"
        b64_data = base64.b64encode(test_image_data).decode()

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = f"data:image/png;base64,{b64_data}"
        mock_response.choices[0].message.images = None
        mock_client.chat.completions.create.return_value = mock_response
        mock_get_client.return_value = mock_client

        from image_gen import generate_image
        generate_image("test prompt", model="custom-model")

        # Verify the custom model was used
        call_kwargs = mock_client.chat.completions.create.call_args
        assert call_kwargs.kwargs["model"] == "custom-model"

    @patch("image_gen.get_openrouter_client")
    def test_handles_list_content_format(self, mock_get_client):
        """Should handle response with list content format."""
        test_image_data = b"image data"
        b64_data = base64.b64encode(test_image_data).decode()

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = [
            {"type": "text", "text": "Here is your image"},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64_data}"}}
        ]
        mock_response.choices[0].message.images = None
        mock_client.chat.completions.create.return_value = mock_response
        mock_get_client.return_value = mock_client

        from image_gen import generate_image
        image_bytes, ext = generate_image("test prompt")

        assert image_bytes == test_image_data
        assert ext == "png"
