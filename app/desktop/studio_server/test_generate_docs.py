import sys
from typing import List

import pytest

from app.desktop.studio_server.finetune_api import (
    FinetuneProviderModel,
    fetch_fireworks_finetune_models,
)
from libs.core.kiln_ai.adapters.ml_model_list import (
    KilnModelProvider,
    ModelProviderName,
    built_in_models,
)
from libs.core.kiln_ai.adapters.provider_tools import provider_name_from_id


def _all_providers_support(providers: List[KilnModelProvider], attribute: str) -> bool:
    """Check if all providers support a given feature"""
    return all(getattr(provider, attribute) for provider in providers)


def _any_providers_support(providers: List[KilnModelProvider], attribute: str) -> bool:
    """Check if any providers support a given feature"""
    return any(getattr(provider, attribute) for provider in providers)


def _get_support_status(providers: List[KilnModelProvider], attribute: str) -> str:
    """Get the support status for a feature"""
    if _all_providers_support(providers, attribute):
        return "✅︎"
    elif _any_providers_support(providers, attribute):
        return "✅︎ (some providers)"
    return ""


def _has_finetune_support(
    providers: List[KilnModelProvider], fireworks_models: List[FinetuneProviderModel]
) -> str:
    """Check if any provider supports fine-tuning"""

    # Check fireworks list
    for provider in providers:
        if provider.name.value == ModelProviderName.fireworks_ai:
            fireworks_id = provider.provider_finetune_id or provider.model_id
            for index, model in enumerate(fireworks_models):
                if model.id == fireworks_id:
                    # We could remove the model from the list so we don't list it again
                    # fireworks_models.pop(index)
                    return "✅︎"

    return "✅︎" if any(p.provider_finetune_id for p in providers) else ""


@pytest.mark.paid(reason="Marking as paid so it isn't run by default")
async def test_generate_model_table():
    """Generate a markdown table of all models and their capabilities"""

    fireworks_models = await fetch_fireworks_finetune_models()

    # Table header
    table = [
        "| Model Name | Providers | Structured Output | Reasoning | Synthetic Data | API Fine-Tuneable |",
        "|------------|-----------|-------------------|-----------|----------------|-------------------|",
    ]

    for model in built_in_models:
        provider_names = ", ".join(
            sorted(provider_name_from_id(p.name.value) for p in model.providers)
        )
        structured_output = _get_support_status(
            model.providers, "supports_structured_output"
        )
        reasoning = _get_support_status(model.providers, "reasoning_capable")
        data_gen = _get_support_status(model.providers, "supports_data_gen")
        finetune = _has_finetune_support(model.providers, fireworks_models)

        row = f"| {model.friendly_name} | {provider_names} | {structured_output} | {reasoning} | {data_gen} | {finetune} |"
        table.append(row)

    # Write the table to stdout (useful for documentation)
    sys.stdout.write("\nModel Capability Matrix:\n")
    sys.stdout.write("\n".join(table))
    sys.stdout.write("\n\nFireworks models remaining:\n")
    sys.stdout.write("- " + "\n- ".join(f"{m.name}" for m in fireworks_models) + "\n\n")

    # Basic assertions to ensure the table is well-formed
    assert len(table) > 2, "Table should have header and at least one row"
    assert all("|" in row for row in table), "All rows should be properly formatted"
    assert len(table[0].split("|")) == len(table[1].split("|")), (
        "Header and separator should have same number of columns"
    )
