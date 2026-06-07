package com.ec26b.shoppingagent.api;

import com.ec26b.shoppingagent.voice.VoiceTranscriber;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.util.LinkedHashMap;
import java.util.Map;

@RestController
@RequestMapping("/api/voice")
public class VoiceController {

    private final VoiceTranscriber transcriber;

    public VoiceController(VoiceTranscriber transcriber) {
        this.transcriber = transcriber;
    }

    @PostMapping("/transcribe")
    public ResponseEntity<ApiResponse<Map<String, Object>>> transcribe(
            @RequestParam("file") MultipartFile file) {
        if (file == null || file.isEmpty()) {
            return ResponseEntity.badRequest()
                    .body(ApiResponse.error(40001, "音频文件不能为空"));
        }
        byte[] audio;
        try {
            audio = file.getBytes();
        } catch (IOException ex) {
            return ResponseEntity.status(500)
                    .body(ApiResponse.error(50000, "读取音频文件失败：" + ex.getMessage()));
        }
        var result = transcriber.transcribe(audio, file.getContentType());
        Map<String, Object> data = new LinkedHashMap<>();
        data.put("text", result.text());
        data.put("provider", result.provider());
        data.put("fallbackUsed", result.fallbackUsed());
        if (result.notice() != null) data.put("notice", result.notice());
        return ResponseEntity.ok(ApiResponse.success(data));
    }
}
