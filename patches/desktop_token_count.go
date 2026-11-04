package cpa

import (
	"encoding/json"
	"errors"
	"strings"
)

func desktopTokenCountRequest(request providerRequest) (providerRequest, error) {
	request.Model = desktopTokenCountModel(request.Model)
	if request.Format != "claude" {
		return request, nil
	}
	var root map[string]any
	if err := json.Unmarshal(request.Payload, &root); err != nil {
		return request, err
	}
	// CPA omits reasoning items from its text counter. Include visible thinking
	// text in this estimate, while keeping opaque signatures out of token text.
	changed := false
	messages, _ := root["messages"].([]any)
	for _, item := range messages {
		message, _ := item.(map[string]any)
		blocks, _ := message["content"].([]any)
		for i, item := range blocks {
			block, _ := item.(map[string]any)
			if block["type"] == "thinking" {
				blocks[i] = map[string]any{"type": "text", "text": block["thinking"]}
				changed = true
			}
		}
	}
	if changed {
		payload, err := json.Marshal(root)
		if err != nil {
			return request, err
		}
		request.Payload = payload
		request.OriginalRequest = append([]byte(nil), payload...)
	}
	return request, nil
}

// GPT-6 has no model-specific encoding in the pinned tokenizer. For local
// estimates only, reuse CPA's GPT-5/o200k encoder and its existing translation
// of tool definitions and tool history. Inference keeps the upstream model.
func desktopTokenCountModel(model string) string {
	name := strings.ToLower(strings.TrimSpace(model))
	if name == "gpt-6" || strings.HasPrefix(name, "gpt-6.") || strings.HasPrefix(name, "gpt-6-") {
		return "gpt-5"
	}
	return model
}

// Validate only self-contained text/tool inputs that CPA's local estimator
// consumes. Media and remote/stateful inputs retain an explicit error.
func validateDesktopClaudeTokenCount(root map[string]any) error {
	if !onlyLocalTokenCountFields(root, "model", "system", "messages", "tools", "tool_choice", "thinking", "metadata", "max_tokens", "temperature", "top_p", "top_k", "stop_sequences", "stream", "output_config") {
		return errors.New("local token count Claude fields are unsupported")
	}
	if system, exists := root["system"]; exists {
		if err := validateDesktopCountContent(system, false, 0); err != nil {
			return err
		}
	}
	if tools, exists := root["tools"]; exists {
		items, ok := tools.([]any)
		if !ok {
			return errors.New("local token count tools must be an array")
		}
		for _, item := range items {
			tool, ok := item.(map[string]any)
			if !ok {
				return errors.New("local token count tool is invalid")
			}
			name, ok := tool["name"].(string)
			if !ok || strings.TrimSpace(name) == "" {
				return errors.New("local token count tool name is required")
			}
			if _, ok := tool["input_schema"].(map[string]any); !ok {
				return errors.New("local token count tool input_schema must be an object")
			}
			if description, exists := tool["description"]; exists && !isString(description) {
				return errors.New("local token count tool description must be text")
			}
		}
	}
	if messages, exists := root["messages"]; exists {
		items, ok := messages.([]any)
		if !ok {
			return errors.New("local token count messages must be an array")
		}
		for _, item := range items {
			message, ok := item.(map[string]any)
			if !ok || !onlyLocalTokenCountFields(message, "role", "content") {
				return errors.New("local token count message is unsupported")
			}
			role, _ := message["role"].(string)
			if role != "user" && role != "assistant" && role != "system" && role != "developer" {
				return errors.New("local token count message role is invalid")
			}
			if err := validateDesktopCountContent(message["content"], true, 0); err != nil {
				return err
			}
		}
	}
	return nil
}

func validateDesktopCountContent(value any, allowTools bool, depth int) error {
	if depth > 32 {
		return errors.New("local token count content is too deeply nested")
	}
	if isString(value) {
		return nil
	}
	items, ok := value.([]any)
	if !ok {
		return errors.New("local token count content must be text or blocks")
	}
	for _, item := range items {
		block, ok := item.(map[string]any)
		if !ok {
			return errors.New("local token count block is invalid")
		}
		switch block["type"] {
		case "text":
			if !isString(block["text"]) || !onlyLocalTokenCountFields(block, "type", "text", "cache_control") {
				return errors.New("local token count text block is invalid")
			}
		case "tool_use":
			if !allowTools || !isString(block["id"]) || !isString(block["name"]) {
				return errors.New("local token count tool_use is invalid")
			}
			if _, ok := block["input"].(map[string]any); !ok {
				return errors.New("local token count tool input must be an object")
			}
		case "tool_result":
			if !allowTools || !isString(block["tool_use_id"]) {
				return errors.New("local token count tool_result is invalid")
			}
			if content, exists := block["content"]; exists {
				if err := validateDesktopCountContent(content, false, depth+1); err != nil {
					return err
				}
			}
		case "thinking":
			if !allowTools || !isString(block["thinking"]) {
				return errors.New("local token count thinking block is invalid")
			}
		default:
			return errors.New("local token count supports text and tool blocks; media and opaque state are unsupported")
		}
	}
	return nil
}
