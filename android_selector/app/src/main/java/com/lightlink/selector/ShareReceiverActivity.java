package com.lightlink.selector;

import android.app.Activity;
import android.content.Intent;
import android.os.Bundle;
import android.widget.Toast;

public class ShareReceiverActivity extends Activity {
    @Override protected void onCreate(Bundle state) {
        super.onCreate(state);
        String text = getIntent().getStringExtra(Intent.EXTRA_TEXT);
        String url = new SelectionStore(this).addFromText(text);
        Toast.makeText(this, url.isEmpty() ? "未识别到抖音链接" : "已加入 LightLink 选片", Toast.LENGTH_SHORT).show();
        finish();
    }
}
