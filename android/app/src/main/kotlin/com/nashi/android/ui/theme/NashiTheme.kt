package com.nashi.android.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color
import com.nashi.android.data.NashiThemeMode

@Immutable
data class NashiPalette(
    val bg: Color,
    val surface: Color,
    val elevated: Color,
    val border: Color,
    val textPrimary: Color,
    val textSecondary: Color,
    val pearGold: Color,
    val accent: Color,
    val success: Color,
    val violet: Color,
    val danger: Color
)

val NashiEdnaPalette = NashiPalette(
    bg = Color(0xFF14151C),
    surface = Color(0xFF1C1E28),
    elevated = Color(0xFF252836),
    border = Color(0x19FFFFFF),
    textPrimary = Color(0xFFEDF0FA),
    textSecondary = Color(0xFF97A0BA),
    pearGold = Color(0xFFF0A868),
    accent = Color(0xFF7C9CFF),
    success = Color(0xFF52D196),
    violet = Color(0xFFC08BFF),
    danger = Color(0xFFFF6E7B)
)

val NashiWarmPalette = NashiPalette(
    bg = Color(0xFF171412),
    surface = Color(0xFF221D1A),
    elevated = Color(0xFF2E2723),
    border = Color(0x1EFFE8D6),
    textPrimary = Color(0xFFFAF3EC),
    textSecondary = Color(0xFFBAA99A),
    pearGold = Color(0xFFF5B26B),
    accent = Color(0xFFE09F5A),
    success = Color(0xFF68D391),
    violet = Color(0xFFD6BCFA),
    danger = Color(0xFFFC8181)
)

val NashiNeutralPalette = NashiPalette(
    bg = Color(0xFF0E0E10),
    surface = Color(0xFF18181B),
    elevated = Color(0xFF242429),
    border = Color(0x1FFFFFFF),
    textPrimary = Color(0xFFFAFAFA),
    textSecondary = Color(0xFFA1A1AA),
    pearGold = Color(0xFFEAB308),
    accent = Color(0xFFE4E4E7),
    success = Color(0xFF4ADE80),
    violet = Color(0xFFA78BFA),
    danger = Color(0xFFF87171)
)

val LocalNashiPalette = staticCompositionLocalOf { NashiEdnaPalette }

@Composable
fun NashiTheme(mode: NashiThemeMode = NashiThemeMode.EDNA, content: @Composable () -> Unit) {
    val palette = when (mode) {
        NashiThemeMode.EDNA -> NashiEdnaPalette
        NashiThemeMode.WARM -> NashiWarmPalette
        NashiThemeMode.NEUTRAL -> NashiNeutralPalette
    }
    val scheme = darkColorScheme(
        primary = palette.pearGold,
        onPrimary = Color(0xFF17120B),
        secondary = palette.accent,
        background = palette.bg,
        onBackground = palette.textPrimary,
        surface = palette.surface,
        onSurface = palette.textPrimary,
        surfaceVariant = palette.elevated,
        onSurfaceVariant = palette.textSecondary,
        error = palette.danger,
        outline = palette.border
    )
    CompositionLocalProvider(LocalNashiPalette provides palette) {
        MaterialTheme(colorScheme = scheme, content = content)
    }
}
