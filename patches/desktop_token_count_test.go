package cpa

import (
	"bytes"
	"encoding/json"
	"strings"
	"testing"
	"time"

	"gpt-load/internal/execution"
	"gpt-load/internal/protocol"
	"gpt-load/internal/subscription/providers/codex"
)

func TestDesktopTokenCountGPT6IsLocalAndKeepsInferenceModel(t *testing.T) {
	for _, model := range []string{"gpt-6.1-sol", "gpt-6.1-terra", "gpt-6-luna"} {
		t.Run(model, func(t *testing.T) {
			adapter, _, _, keys, row := newAdapterFixture(t, credentialJSON("access", "refresh", time.Now().Add(time.Hour)))
			preparer := &fakeCredentialPreparer{delegate: adapter.credentials}
			adapter.credentials = preparer
			fake := &fakeExecutor{countResult: codex.ExecuteResponse{Payload: []byte(`{"input_tokens":7}`)}}
			setCodexExecutor(t, adapter, fake)
			spec := validSpec(t, row, keys)
			spec.ClientProtocol = protocol.Anthropic
			spec.Operation = execution.OperationCountTokens
			spec.RouteMode = execution.RouteConverted
			spec.ClientModel = "claude-opus-5-5"
			spec.UpstreamModel = model
			spec.Body = []byte(`{"model":"claude-opus-5-5","messages":[{"role":"user","content":"你好"}]}`)
			result := adapter.Execute(t.Context(), spec)
			if result.Error != nil || result.DispatchState != execution.DispatchLocal ||
				result.Header.Get(localTokenCountHeader) != "local-estimate" ||
				preparer.calls != 0 || fake.calls != 0 || fake.countCalls != 1 || fake.request.Model != "gpt-5" {
				t.Fatalf("count result=%#v prepares=%d inference=%d count=%d model=%s", result, preparer.calls, fake.calls, fake.countCalls, fake.request.Model)
			}
			if spec.UpstreamModel != model || !bytes.Contains(spec.Body, []byte("claude-opus-5-5")) {
				t.Fatal("count operation mutated the inference model or original body")
			}
		})
	}
}

func TestDesktopTokenCountRealCodecIncludesToolsAndHistory(t *testing.T) {
	bridge := newCodexProviderBridge()
	count := func(body string) int64 {
		t.Helper()
		request := providerRequest{Model: "gpt-6.1-sol", Format: "claude", Payload: []byte(body)}
		if err := bridge.ValidateLocalTokenCount(request); err != nil {
			t.Fatal(err)
		}
		response, err := bridge.CountTokensLocal(t.Context(), request)
		if err != nil {
			t.Fatal(err)
		}
		var result struct {
			InputTokens int64 `json:"input_tokens"`
		}
		if err := json.Unmarshal(response.Payload, &result); err != nil || result.InputTokens <= 0 || response.Headers.Get(localTokenCountHeader) != "local-estimate" {
			t.Fatalf("invalid count result: %s / %v", response.Payload, err)
		}
		return result.InputTokens
	}
	base := count(`{"model":"gpt-6.1-sol","messages":[{"role":"user","content":"hello 你好"}]}`)
	tools := count(`{"model":"gpt-6.1-sol","system":[{"type":"text","text":"You are helpful.","cache_control":{"type":"ephemeral"}}],"tools":[{"name":"read_file","description":"Read a UTF-8 file from the workspace","input_schema":{"type":"object","properties":{"path":{"type":"string"}},"required":["path"]},"cache_control":{"type":"ephemeral"}}],"messages":[{"role":"user","content":"hello 你好"},{"role":"assistant","content":[{"type":"tool_use","id":"call_1","name":"read_file","input":{"path":"notes.txt"}}]},{"role":"user","content":[{"type":"tool_result","tool_use_id":"call_1","content":[{"type":"text","text":"The shared family budget is 2000 per month.","cache_control":{"type":"ephemeral"}}]}]}]}`)
	if tools <= base {
		t.Fatalf("tools and tool history were omitted: base=%d tools=%d", base, tools)
	}
	long := count(`{"model":"gpt-6.1-sol","messages":[{"role":"user","content":` + jsonString(strings.Repeat("hello 你好 ", 1000)) + `}]}`)
	if long <= tools {
		t.Fatalf("long prompt did not increase count: tools=%d long=%d", tools, long)
	}
	thinking := count(`{"model":"gpt-6.1-sol","messages":[{"role":"assistant","content":[{"type":"thinking","thinking":` + jsonString(strings.Repeat("consider the file contents ", 100)) + `,"signature":"opaque-signature"},{"type":"text","text":"hello 你好"}]}]}`)
	if thinking <= base {
		t.Fatal("visible thinking text was omitted")
	}
}

func jsonString(value string) string {
	raw, _ := json.Marshal(value)
	return string(raw)
}

func TestDesktopTokenCountRejectsUnsupportedInput(t *testing.T) {
	for _, body := range []string{
		`null`, `{`,
		`{"messages":{}}`,
		`{"messages":[{"role":"user","content":12}]}`,
		`{"messages":[{"role":"invalid-role","content":"hello"}]}`,
		`{"messages":[{"role":"user","content":[{"type":"image","source":{"type":"url","url":"https://example.invalid/image.png"}}]}]}`,
		`{"messages":[{"role":"user","content":[{"type":"tool_result","tool_use_id":"a","content":[{"type":"document","source":{"type":"base64","data":"AAAA"}}]}]}]}`,
		`{"tools":[{"name":"read_file","input_schema":42}]}`,
		`{"previous_response_id":"resp_123","messages":[]}`,
	} {
		if err := newCodexProviderBridge().ValidateLocalTokenCount(providerRequest{Model: "gpt-6.1-sol", Format: "claude", Payload: []byte(body)}); err == nil {
			t.Errorf("accepted unsupported body: %s", body)
		}
	}
}
