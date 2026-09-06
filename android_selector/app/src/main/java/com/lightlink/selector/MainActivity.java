package com.lightlink.selector;

import android.app.Activity;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.view.View;
import android.widget.Button;
import android.widget.CheckBox;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;

public class MainActivity extends Activity {
    private SelectionStore store;
    private LinearLayout list;
    private TextView header;

    @Override protected void onCreate(Bundle state) {
        super.onCreate(state);
        store = new SelectionStore(this);
        readConfiguration();
        buildUi();
    }

    @Override protected void onResume() {
        super.onResume();
        if (list != null) refresh();
    }

    private void readConfiguration() {
        Uri data = getIntent().getData();
        if (data == null || !"configure".equals(data.getHost())) return;
        try {
            store.configure(
                Integer.parseInt(data.getQueryParameter("task_id")),
                Integer.parseInt(data.getQueryParameter("port")),
                data.getQueryParameter("token")
            );
        } catch (Exception ignored) { }
    }

    private void buildUi() {
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(32, 28, 32, 20);
        header = new TextView(this);
        header.setTextSize(22);
        header.setTextColor(Color.BLACK);
        root.addView(header);

        TextView help = new TextView(this);
        help.setText("在抖音视频中点 分享 → 更多 → LightLink 选片，可连续加入多个视频。\n勾选后提交到 Windows 工具。 ");
        help.setTextSize(16);
        help.setPadding(0, 16, 0, 20);
        root.addView(help);

        ScrollView scroll = new ScrollView(this);
        list = new LinearLayout(this);
        list.setOrientation(LinearLayout.VERTICAL);
        scroll.addView(list);
        root.addView(scroll, new LinearLayout.LayoutParams(-1, 0, 1));

        LinearLayout actions = new LinearLayout(this);
        Button all = button("全选", v -> setAll(true));
        Button remove = button("删除所选", v -> deleteSelected());
        Button submit = button("提交所选", v -> submitSelected());
        actions.addView(all, new LinearLayout.LayoutParams(0, -2, 1));
        actions.addView(remove, new LinearLayout.LayoutParams(0, -2, 1));
        actions.addView(submit, new LinearLayout.LayoutParams(0, -2, 1));
        root.addView(actions);
        setContentView(root);
        refresh();
    }

    private Button button(String label, View.OnClickListener listener) {
        Button button = new Button(this);
        button.setText(label);
        button.setOnClickListener(listener);
        return button;
    }

    private void refresh() {
        header.setText("LightLink 选片 · Odoo任务 " + (store.taskId() == 0 ? "未配置" : store.taskId()));
        list.removeAllViews();
        for (String url : store.list()) {
            CheckBox box = new CheckBox(this);
            box.setTag(url);
            box.setChecked(true);
            box.setText("[" + store.status(url) + "] " + url);
            box.setTextSize(15);
            box.setPadding(0, 8, 0, 8);
            list.addView(box);
        }
    }

    private List<String> selected() {
        List<String> result = new ArrayList<>();
        for (int i = 0; i < list.getChildCount(); i++) {
            CheckBox box = (CheckBox) list.getChildAt(i);
            if (box.isChecked()) result.add((String) box.getTag());
        }
        return result;
    }

    private void setAll(boolean checked) {
        for (int i = 0; i < list.getChildCount(); i++) ((CheckBox) list.getChildAt(i)).setChecked(checked);
    }

    private void deleteSelected() {
        List<String> urls = selected();
        if (urls.isEmpty()) return;
        store.delete(urls);
        refresh();
    }

    private void submitSelected() {
        List<String> urls = selected();
        if (urls.isEmpty()) {
            Toast.makeText(this, "请先勾选视频", Toast.LENGTH_SHORT).show();
            return;
        }
        if (store.taskId() == 0 || store.port() == 0 || store.token().isEmpty()) {
            Toast.makeText(this, "请先从 Windows 工具启动 Odoo 选片任务", Toast.LENGTH_LONG).show();
            return;
        }
        new Thread(() -> post(urls)).start();
    }

    private void post(List<String> urls) {
        HttpURLConnection connection = null;
        try {
            JSONObject payload = new JSONObject();
            payload.put("task_id", store.taskId());
            payload.put("urls", new JSONArray(urls));
            byte[] body = payload.toString().getBytes(StandardCharsets.UTF_8);
            connection = (HttpURLConnection) new URL(
                "http://127.0.0.1:" + store.port() + "/selection/submit"
            ).openConnection();
            connection.setRequestMethod("POST");
            connection.setRequestProperty("Content-Type", "application/json; charset=utf-8");
            connection.setRequestProperty("X-LightLink-Token", store.token());
            connection.setConnectTimeout(5000);
            connection.setReadTimeout(5000);
            connection.setDoOutput(true);
            try (OutputStream output = connection.getOutputStream()) { output.write(body); }
            if (connection.getResponseCode() != 200) throw new IllegalStateException("HTTP " + connection.getResponseCode());
            store.markSubmitted(urls);
            runOnUiThread(() -> { refresh(); Toast.makeText(this, "已提交到 Windows 工具", Toast.LENGTH_LONG).show(); });
        } catch (Exception exc) {
            String message = exc.getMessage();
            runOnUiThread(() -> Toast.makeText(this, "提交失败：" + message, Toast.LENGTH_LONG).show());
        } finally {
            if (connection != null) connection.disconnect();
        }
    }
}
