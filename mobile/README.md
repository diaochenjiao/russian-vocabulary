# 独立安卓版本
内置5505条词汇、5份真题索引及124183种词形映射。离线FSRS、新词10词分组、到期复习、收藏、词典及备份。
本地构建：Node24+、JDK21、Android SDK36；npm ci，npm run build，npx cap sync android，cd android，gradlew assembleDebug。
GitHub Actions自动构建的调试APK用于安装测试；尚未真机验收，不是商店正式发布包。
AI需填写自己的Key，本次打开有效，关闭后不保留；Key不包含在APK内或学习备份内。AI和发音需要联网。新试卷和Word导入暂不支持。
原件查看与备份通过Android分享菜单交给文件应用；需安装PDF/Word阅读器。
学习数据留在应用私有存储，卸载前导出备份；应用更新应使用相同签名，否则需先备份再卸载旧版。
