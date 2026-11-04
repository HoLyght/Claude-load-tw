# Desktop Token count compatibility patch

Base: GPT-Load v2.0.0-rc.59, upstream commit `53a07e4932a25954dc56fbdc11e79a2796ed659f`.

The existing Codex estimator rejects GPT-6 model IDs before dispatch. Its text-only validator also rejects tool definitions, tool history, and cache annotations sent by Desktop.

This patch reuses CPA's existing offline tool/message translation and local token counter. Only local GPT-6 token-count requests select the GPT-5/o200k tokenizer. This is an approximation, identified by the existing `X-GPT-Load-Token-Count: local-estimate` header. The inference model, alias routing, authentication, proxy, and upstream generation requests keep their original values.

Supported count inputs: plain text, cached system/text blocks, custom tool schemas, tool calls and text tool results, visible thinking text. Visible thinking text is included in the estimate; opaque signatures are excluded. Media/document blocks and stateful/remote references remain unsupported and return an error. The counts are planning estimates; upstream generation usage remains authoritative.

Builds download the fixed upstream commit, verify its archive SHA256, apply the small guarded patch, run CPA/Codex package tests, build the original frontend and patched binary, and copy that binary into the existing Taiwan/Mihomo image. No database migration or configuration change is introduced.

Version: `v2.0.0-rc.59+desktop-count.1`.

Tests cover all three GPT-6 models, no OAuth preparation or inference dispatch during counting, original input/model preservation, real-codec tool history and long prompts, and explicit rejection of unsupported inputs. The original package tests also run in the image build.
