"""Schemas for non-`KnowledgeRecord` knowledge files.

`knowledge/core/` holds two different kinds of YAML:

  * curated lessons/rules  -> `KnowledgeRecord` (models/knowledge.py)
  * source/fee configuration -> the models in this module

Without a separate schema, the generic loader would try to parse a source
allowlist as a lesson and fail validation.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class SourceTier(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tier: str
    domains: list[str] = Field(default_factory=list)
    #: True only for primary/official data. Lower tiers may inform a narrative
    #: but must never override numerical market data.
    can_override_data: bool = False


class SourceRules(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_pages_per_run: int = Field(default=8, ge=1)
    fetch_timeout_seconds: int = Field(default=15, ge=1)
    max_chars_per_page: int = Field(default=4000, ge=100)
    #: Web content is untrusted input, never instructions.
    content_is_untrusted: bool = True
    block_login_walled_content: bool = True


class TrustedSources(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_tiers: list[SourceTier] = Field(default_factory=list)
    rules: SourceRules = Field(default_factory=SourceRules)

    def all_domains(self) -> set[str]:
        return {d.lower() for tier in self.source_tiers for d in tier.domains}

    def tier_for(self, host: str) -> str:
        host = host.lower()
        for tier in self.source_tiers:
            for domain in tier.domains:
                if host == domain or host.endswith("." + domain):
                    return tier.tier
        return "general"

    def domains_for_tier(self, name: str) -> set[str]:
        return {
            d.lower()
            for tier in self.source_tiers
            if tier.tier == name
            for d in tier.domains
        }
