"""Apply the small token-count patch to the pinned GPT-Load rc.59 source."""
from pathlib import Path
import shutil
import sys

source = Path(sys.argv[1]).resolve()
patches = Path(__file__).resolve().parent
target = source / "internal/execution/cpa/codex_provider.go"
text = target.read_text(encoding="utf-8")

def replace_once(old, new):
    global text
    if text.count(old) != 1:
        raise SystemExit("Pinned source changed; refusing to apply token-count patch")
    text = text.replace(old, new, 1)

replace_once(
    '\tresponse, err := bridge.executor.CountTokens(ctx, "local-token-count", codex.Credential{}, codex.ExecuteRequest{',
    '\trequest, err := desktopTokenCountRequest(request)\n\tif err != nil {\n\t\treturn providerResponse{}, err\n\t}\n\tresponse, err := bridge.executor.CountTokens(ctx, "local-token-count", codex.Credential{}, codex.ExecuteRequest{',
)
replace_once(
    '\tif !localTokenCountModelSupported(request.Model) {',
    '\tif !localTokenCountModelSupported(desktopTokenCountModel(request.Model)) {',
)
replace_once(
    '\tcase "claude":\n\t\treturn validateLocalClaudeTokenCount(root)',
    '\tcase "claude":\n\t\treturn validateDesktopClaudeTokenCount(root)',
)
target.write_text(text, encoding="utf-8", newline="\n")
for name in ("desktop_token_count.go", "desktop_token_count_test.go"):
    shutil.copyfile(patches / name, target.parent / name)
print("Applied Desktop token-count compatibility patch")
