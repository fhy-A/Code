package claude_test

import (
 "bytes"
 "encoding/json"
 "io"
 "net/http"
 "net/http/httptest"
 "testing"

 "github.com/QuantumNous/new-api/dto"
 "github.com/QuantumNous/new-api/relay/channel/claude"
 "github.com/QuantumNous/new-api/relay/channel/deepseek"
 relaycommon "github.com/QuantumNous/new-api/relay/common"
 "github.com/QuantumNous/new-api/types"
 "github.com/gin-gonic/gin"
 "github.com/stretchr/testify/assert"
 "github.com/stretchr/testify/require"
)

// Run only through the documented Go overlay, outside the gateway worktree.
// No database, credential store, normal gateway service or paid upstream is used.
func TestCode083NativeReplayRoundtrip(t *testing.T) {
 gin.SetMode(gin.TestMode)
 for _, effort := range []string{"default", "low", "medium", "high"} {
  t.Run("claude-"+effort, func(t *testing.T) {
   body := `{"model":"claude-opus-4-6","max_tokens":8192,"thinking":{"type":"adaptive"},"output_config":{"effort":"`+effort+`"},"messages":[{"role":"assistant","content":[{"type":"thinking","thinking":"private","signature":"opaque-signature"},{"type":"redacted_thinking","data":"opaque-data"},{"type":"tool_use","id":"tool1","name":"lookup","input":{}}]},{"role":"user","content":[{"type":"tool_result","tool_use_id":"tool1","content":"found"}]}]}`
   var incoming dto.ClaudeRequest
   if effort == "default" {
    var fields map[string]any
    require.NoError(t,json.Unmarshal([]byte(body),&fields))
    delete(fields,"thinking"); delete(fields,"output_config")
    data,err := json.Marshal(fields); require.NoError(t,err); body=string(data)
   }
   require.NoError(t,json.Unmarshal([]byte(body), &incoming))
   recorder := httptest.NewRecorder()
   ctx,_ := gin.CreateTestContext(recorder)
   ctx.Request = httptest.NewRequest("POST", "/v1/messages", nil)
   info := &relaycommon.RelayInfo{RelayFormat:types.RelayFormatClaude, ChannelMeta:&relaycommon.ChannelMeta{UpstreamModelName:incoming.Model}}
   adaptor := &claude.Adaptor{}
   converted,err := adaptor.ConvertClaudeRequest(ctx,info,&incoming)
   require.NoError(t,err)
   wire,err := json.Marshal(converted)
   require.NoError(t,err)
   var observed map[string]any
   upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter,r *http.Request){
    require.NoError(t,json.NewDecoder(r.Body).Decode(&observed))
    w.Header().Set("Content-Type","application/json")
    _,_ = io.WriteString(w,`{"id":"msg1","type":"message","role":"assistant","model":"claude-opus-4-6","content":[{"type":"thinking","thinking":"private","signature":"opaque-signature"},{"type":"redacted_thinking","data":"opaque-data"},{"type":"text","text":"done"}],"stop_reason":"end_turn","usage":{"input_tokens":5,"output_tokens":5}}`)
   }))
   defer upstream.Close()
   response,err := http.Post(upstream.URL,"application/json",bytes.NewReader(wire))
   require.NoError(t,err)
   _,apiErr := adaptor.DoResponse(ctx,response,info)
   require.Nil(t,apiErr)
   if effort == "default" { assert.Nil(t,observed["output_config"]); assert.Nil(t,observed["thinking"]) } else {
    assert.Equal(t,effort,observed["output_config"].(map[string]any)["effort"])
   }
   assert.Contains(t,string(wire),"opaque-signature")
   assert.Contains(t,string(wire),"opaque-data")
   assert.Contains(t,recorder.Body.String(),"opaque-signature")
   assert.Contains(t,recorder.Body.String(),"opaque-data")
   stream := httptest.NewRecorder()
   streamCtx,_ := gin.CreateTestContext(stream)
   streamCtx.Request = httptest.NewRequest("POST","/v1/messages",nil)
   chunk := `{"type":"content_block_delta","index":0,"delta":{"type":"signature_delta","signature":"opaque-stream-signature"}}`
   require.Nil(t,claude.HandleStreamResponseData(streamCtx,info,&claude.ClaudeResponseInfo{Usage:&dto.Usage{}},chunk))
   assert.Contains(t,stream.Body.String(),chunk)
  })
 }
 for _,model := range []string{"deepseek-v4-flash","deepseek-v4-pro","deepseek-v4-flash-vision-exp"} {
  for _,effort := range []string{"default","low","high","max"} {
   t.Run(model+"-"+effort,func(t *testing.T){
    body := `{"model":"`+model+`","max_tokens":4096,"reasoning_effort":"`+effort+`","thinking":{"type":"enabled"},"messages":[{"role":"assistant","content":"done","reasoning_content":"private-round-one"},{"role":"user","content":"continue"}]}`
    var incoming dto.GeneralOpenAIRequest
    if effort == "default" {
     var fields map[string]any
     require.NoError(t,json.Unmarshal([]byte(body),&fields))
     delete(fields,"thinking"); delete(fields,"reasoning_effort")
     data,err := json.Marshal(fields); require.NoError(t,err); body=string(data)
    }
    require.NoError(t,json.Unmarshal([]byte(body),&incoming))
    recorder := httptest.NewRecorder()
    ctx,_ := gin.CreateTestContext(recorder)
    ctx.Request=httptest.NewRequest("POST","/v1/chat/completions",nil)
    info := &relaycommon.RelayInfo{RelayFormat:types.RelayFormatOpenAI,ChannelMeta:&relaycommon.ChannelMeta{UpstreamModelName:model}}
    adaptor := &deepseek.Adaptor{}
    converted,err := adaptor.ConvertOpenAIRequest(ctx,info,&incoming)
    require.NoError(t,err)
    wire,err := json.Marshal(converted)
    require.NoError(t,err)
    var observed map[string]any
    upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter,r *http.Request){
     require.NoError(t,json.NewDecoder(r.Body).Decode(&observed))
     w.Header().Set("Content-Type","application/json")
     _,_ = io.WriteString(w,`{"id":"chat1","choices":[{"index":0,"message":{"role":"assistant","content":"done","reasoning_content":"private-round-two"},"finish_reason":"stop"}],"usage":{"prompt_tokens":5,"completion_tokens":5,"total_tokens":10}}`)
    }))
    defer upstream.Close()
    response,err := http.Post(upstream.URL,"application/json",bytes.NewReader(wire))
    require.NoError(t,err)
    _,apiErr := adaptor.DoResponse(ctx,response,info)
    require.Nil(t,apiErr)
    if effort == "default" { assert.Nil(t,observed["reasoning_effort"]); assert.Nil(t,observed["thinking"]) } else {
     assert.Equal(t,effort,observed["reasoning_effort"])
    }
    assert.Equal(t,model,observed["model"])
    assert.Contains(t,string(wire),"private-round-one")
    assert.Contains(t,recorder.Body.String(),"private-round-two")
   })
  }
 }
}
