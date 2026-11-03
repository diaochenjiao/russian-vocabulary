package cn.russian.vocabulary;

import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.speech.tts.TextToSpeech;
import android.util.Base64;
import com.getcapacitor.*;
import com.getcapacitor.annotation.CapacitorPlugin;
import java.security.KeyStore;
import java.util.Locale;
import javax.crypto.*;
import javax.crypto.spec.GCMParameterSpec;

@CapacitorPlugin(name = "StudyDevice")
public class StudyDevice extends Plugin {
    private TextToSpeech speech;
    private boolean speechReady;
    private static final String ALIAS = "study-deepseek-v1";

    @Override public void load() {
        getActivity().runOnUiThread(() ->
            speech = new TextToSpeech(getContext(), status -> speechReady = status == TextToSpeech.SUCCESS));
    }

    @PluginMethod public void speak(PluginCall call) {
        getActivity().runOnUiThread(() -> {
            if (!speechReady || speech == null ||
                speech.setLanguage(Locale.forLanguageTag("ru-RU")) < 0) {
                call.reject("系统俄语语音不可用，请在安卓文字转语音设置中安装俄语语音。");
                return;
            }
            int result = speech.speak(call.getString("text", ""), TextToSpeech.QUEUE_FLUSH, null, "word");
            if (result == TextToSpeech.SUCCESS) call.resolve();
            else call.reject("系统朗读失败");
        });
    }

    @Override protected void handleOnDestroy() {
        if (speech != null) speech.shutdown();
        super.handleOnDestroy();
    }

    private SecretKey secret() throws Exception {
        KeyStore store = KeyStore.getInstance("AndroidKeyStore");
        store.load(null);
        if (store.containsAlias(ALIAS)) return (SecretKey) store.getKey(ALIAS, null);
        KeyGenerator generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore");
        generator.init(new KeyGenParameterSpec.Builder(ALIAS,
            KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT)
            .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
            .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).build());
        return generator.generateKey();
    }

    @PluginMethod public void saveKey(PluginCall call) {
        try {
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.ENCRYPT_MODE, secret());
            String iv = Base64.encodeToString(cipher.getIV(), Base64.NO_WRAP);
            String encrypted = Base64.encodeToString(cipher.doFinal(
                call.getString("key", "").getBytes(java.nio.charset.StandardCharsets.UTF_8)), Base64.NO_WRAP);
            if (!getContext().getSharedPreferences("study-secrets", 0).edit().putString("deepseek", iv + ":" + encrypted).commit())
                throw new IllegalStateException();
            call.resolve();
        } catch (Exception e) { call.reject("API Key 保存失败"); }
    }

    @PluginMethod public void readKey(PluginCall call) {
        JSObject result = new JSObject();
        try {
            String saved = getContext().getSharedPreferences("study-secrets", 0).getString("deepseek", "");
            if (!saved.isEmpty()) {
                String[] parts = saved.split(":", 2);
                Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
                cipher.init(Cipher.DECRYPT_MODE, secret(), new GCMParameterSpec(128, Base64.decode(parts[0], Base64.NO_WRAP)));
                result.put("key", new String(cipher.doFinal(Base64.decode(parts[1], Base64.NO_WRAP)),
                    java.nio.charset.StandardCharsets.UTF_8));
            }
        } catch (Exception e) { call.reject("无法读取已保存的 API Key"); return; }
        call.resolve(result);
    }
}
