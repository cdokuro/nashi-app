package com.nashi.android.ui.components

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.nashi.android.ui.theme.LocalNashiPalette
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.roundToInt
import kotlin.math.sin

data class WheelAction(
    val id: String,
    val label: String,
    val subtitle: String = "",
    val icon: ImageVector,
    val tint: Color
)

@Composable
fun RadialConversionWheel(
    centerTitle: String,
    centerSubtitle: String,
    actions: List<WheelAction>,
    busy: Boolean,
    progress: Float?,
    onSelect: (WheelAction) -> Unit,
    modifier: Modifier = Modifier
) {
    val palette = LocalNashiPalette.current
    val haptic = LocalHapticFeedback.current
    val wheelSize = 326.dp
    val orbitRadiusDp = 118.dp

    Box(
        modifier = modifier.fillMaxWidth().height(wheelSize),
        contentAlignment = Alignment.Center
    ) {
        // Subtle radial guide rings
        Canvas(modifier = Modifier.size(wheelSize)) {
            val c = Offset(size.width / 2f, size.height / 2f)
            drawCircle(
                color = palette.border,
                radius = size.minDimension * 0.365f,
                center = c,
                style = Stroke(width = 2f)
            )
            drawCircle(
                color = palette.pearGold.copy(alpha = 0.14f),
                radius = size.minDimension * 0.18f,
                center = c,
                style = Stroke(width = 2.5f)
            )
            if (actions.isNotEmpty()) {
                val step = (2.0 * PI) / actions.size
                for (i in actions.indices) {
                    val ang = -PI / 2.0 + i * step
                    val r1 = size.minDimension * 0.19f
                    val r2 = size.minDimension * 0.31f
                    drawLine(
                        color = palette.border,
                        start = Offset((c.x + r1 * cos(ang)).toFloat(), (c.y + r1 * sin(ang)).toFloat()),
                        end = Offset((c.x + r2 * cos(ang)).toFloat(), (c.y + r2 * sin(ang)).toFloat()),
                        strokeWidth = 1.5f
                    )
                }
            }
        }

        // Center Hub
        Surface(
            shape = CircleShape,
            color = palette.surface,
            border = BorderStroke(1.5.dp, palette.pearGold.copy(alpha = 0.65f)),
            shadowElevation = 8.dp,
            modifier = Modifier.size(112.dp)
        ) {
            Box(contentAlignment = Alignment.Center, modifier = Modifier.fillMaxSize().padding(10.dp)) {
                if (busy) {
                    if (progress != null && progress > 0f && progress < 1f) {
                        CircularProgressIndicator(
                            progress = { progress },
                            color = palette.pearGold,
                            strokeWidth = 3.5.dp,
                            modifier = Modifier.size(56.dp)
                        )
                    } else {
                        CircularProgressIndicator(
                            color = palette.pearGold,
                            strokeWidth = 3.5.dp,
                            modifier = Modifier.size(44.dp)
                        )
                    }
                } else {
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Text(
                            text = centerTitle,
                            color = palette.textPrimary,
                            fontSize = 12.5.sp,
                            fontWeight = FontWeight.Bold,
                            maxLines = 2,
                            overflow = TextOverflow.Ellipsis,
                            textAlign = TextAlign.Center
                        )
                        if (centerSubtitle.isNotBlank()) {
                            Spacer(Modifier.height(2.dp))
                            Text(
                                text = centerSubtitle,
                                color = palette.pearGold,
                                fontSize = 10.5.sp,
                                maxLines = 1,
                                overflow = TextOverflow.Ellipsis
                            )
                        }
                    }
                }
            }
        }

        // Orbiting Radial Action Nodes
        if (actions.isNotEmpty()) {
            val step = (2.0 * PI) / actions.size
            actions.forEachIndexed { idx, action ->
                val angle = -PI / 2.0 + idx * step
                val dx = (orbitRadiusDp.value * cos(angle)).dp
                val dy = (orbitRadiusDp.value * sin(angle)).dp
                Surface(
                    shape = RoundedCornerShape(16.dp),
                    color = palette.surface,
                    border = BorderStroke(1.dp, action.tint.copy(alpha = 0.48f)),
                    shadowElevation = 6.dp,
                    modifier = Modifier
                        .offset(x = dx, y = dy)
                        .clip(RoundedCornerShape(16.dp))
                        .clickable(enabled = !busy) {
                            haptic.performHapticFeedback(HapticFeedbackType.LongPress)
                            onSelect(action)
                        }
                ) {
                    Column(
                        modifier = Modifier.padding(horizontal = 10.dp, vertical = 8.dp),
                        horizontalAlignment = Alignment.CenterHorizontally,
                        verticalArrangement = Arrangement.Center
                    ) {
                        Icon(action.icon, action.label, tint = action.tint, modifier = Modifier.size(19.dp))
                        Spacer(Modifier.height(2.dp))
                        Text(
                            text = action.label,
                            color = palette.textPrimary,
                            fontSize = 11.sp,
                            fontWeight = FontWeight.SemiBold,
                            maxLines = 1
                        )
                    }
                }
            }
        }
    }
}
