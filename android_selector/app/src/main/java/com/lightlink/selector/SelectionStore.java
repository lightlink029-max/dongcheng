package com.lightlink.selector;

import android.content.Context;
import android.content.SharedPreferences;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

final class SelectionStore {
    private static final String PREFS = "lightlink_selection";
    private static final Pattern URL = Pattern.compile("https?://(?:www\\.)?(?:v\\.)?(?:douyin\\.com|iesdouyin\\.com)/[^\\s<>]+", Pattern.CASE_INSENSITIVE);
    private final SharedPreferences prefs;

    SelectionStore(Context context) {
        prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }

    String addFromText(String text) {
        Matcher matcher = URL.matcher(text == null ? "" : text);
        if (!matcher.find()) return "";
        String url = matcher.group().replaceAll("[，。；,;!！?？)\\]}]+$", "");
        Set<String> urls = new LinkedHashSet<>(prefs.getStringSet("urls", new LinkedHashSet<>()));
        urls.add(url);
        prefs.edit().putStringSet("urls", urls).putString("status_" + url, "待提交").apply();
        return url;
    }

    List<String> list() {
        return new ArrayList<>(prefs.getStringSet("urls", new LinkedHashSet<>()));
    }

    String status(String url) { return prefs.getString("status_" + url, "待提交"); }

    void markSubmitted(List<String> urls) {
        SharedPreferences.Editor editor = prefs.edit();
        for (String url : urls) editor.putString("status_" + url, "已提交");
        editor.apply();
    }

    void delete(List<String> selected) {
        Set<String> urls = new LinkedHashSet<>(prefs.getStringSet("urls", new LinkedHashSet<>()));
        urls.removeAll(selected);
        SharedPreferences.Editor editor = prefs.edit().putStringSet("urls", urls);
        for (String url : selected) editor.remove("status_" + url);
        editor.apply();
    }

    void configure(int taskId, int port, String token) {
        prefs.edit().putInt("task_id", taskId).putInt("port", port).putString("token", token).apply();
    }

    int taskId() { return prefs.getInt("task_id", 0); }
    int port() { return prefs.getInt("port", 0); }
    String token() { return prefs.getString("token", ""); }
}
