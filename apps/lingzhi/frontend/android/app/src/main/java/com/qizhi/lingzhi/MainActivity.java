package com.qizhi.lingzhi;

import android.os.Bundle;
import android.webkit.WebView;
import androidx.activity.OnBackPressedCallback;
import androidx.appcompat.app.AlertDialog;
import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        getOnBackPressedDispatcher().addCallback(this, new OnBackPressedCallback(true) {
            @Override
            public void handleOnBackPressed() {
                WebView webView = getBridge() == null ? null : getBridge().getWebView();
                if (webView != null && webView.canGoBack()) {
                    webView.goBack();
                    return;
                }

                new AlertDialog.Builder(MainActivity.this)
                    .setTitle("退出灵知？")
                    .setMessage("确定要退出灵知吗？")
                    .setNegativeButton("继续学习", (dialog, which) -> dialog.dismiss())
                    .setPositiveButton("退出", (dialog, which) -> finish())
                    .show();
            }
        });
    }
}
