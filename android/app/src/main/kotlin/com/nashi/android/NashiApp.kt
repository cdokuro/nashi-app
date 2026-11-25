package com.nashi.android

import android.app.Application
import com.nashi.android.data.NashiRepository

class NashiApp : Application() {
    lateinit var repository: NashiRepository
        private set

    override fun onCreate() {
        super.onCreate()
        instance = this
        repository = NashiRepository(this)
    }

    companion object {
        @Volatile
        lateinit var instance: NashiApp
            private set
    }
}
