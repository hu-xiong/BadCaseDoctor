package com.farm.calculator.scheduler;

import com.farm.calculator.service.NotificationService;
import com.farm.calculator.service.PlantationService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/**
 * 定时任务：每分钟检查浇水提醒和超时
 */
@Component
public class WateringReminderTask {

    private static final Logger log = LoggerFactory.getLogger(WateringReminderTask.class);

    @Autowired
    private NotificationService notificationService;

    @Autowired
    private PlantationService plantationService;

    @Scheduled(fixedRate = 60000)
    public void checkWateringReminders() {
        try {
            // 检查超时
            plantationService.checkOverdue();
            // 发送提醒
            notificationService.checkAndNotify();
        } catch (Exception e) {
            log.error("定时任务执行出错: {}", e.getMessage());
        }
    }
}
