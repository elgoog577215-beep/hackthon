# Keep kotlinx.serialization metadata.
-keepattributes *Annotation*, InnerClasses
-dontnote kotlinx.serialization.AnnotationsKt
-keep,includedescriptorclasses class com.mentorai.app.**$$serializer { *; }
-keepclassmembers class com.mentorai.app.** {
    *** Companion;
}
-keepclasseswithmembers class com.mentorai.app.** {
    kotlinx.serialization.KSerializer serializer(...);
}
