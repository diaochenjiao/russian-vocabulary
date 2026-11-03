package cn.russian.vocabulary;

import android.os.Bundle;
import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    @Override public void onCreate(Bundle savedInstanceState) {
        registerPlugin(StudyDevice.class);
        super.onCreate(savedInstanceState);
    }
}
