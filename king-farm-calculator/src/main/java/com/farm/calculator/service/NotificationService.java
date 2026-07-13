package com.farm.calculator.service;

import com.farm.calculator.model.Plantation;
import com.farm.calculator.model.User;
import com.farm.calculator.repository.PlantationRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.List;

/**
 * 邮件通知服务
 */
@Service
public class NotificationService {

    private static final Logger log = LoggerFactory.getLogger(NotificationService.class);

    @Autowired(required = false)
    private JavaMailSender mailSender;

    @Autowired
    private PlantationRepository plantationRepository;

    @Value("${spring.mail.username:}")
    private String mailFrom;

    @Value("${app.notify.before-minutes:30}")
    private int notifyBeforeMinutes;

    /**
     * 扫描需要提醒的种植记录并发送邮件
     */
    public void checkAndNotify() {
        if (mailSender == null) {
            return; // 未配置邮件则不发送
        }

        LocalDateTime now = LocalDateTime.now();
        LocalDateTime start = now;
        LocalDateTime end = now.plusMinutes(notifyBeforeMinutes);

        List<Plantation> toNotify = plantationRepository
                .findByStatusAndNotifiedAndNextWateringTimeBetween(
                        Plantation.Status.GROWING, false, start, end);

        for (Plantation p : toNotify) {
            try {
                sendWateringReminder(p);
                p.setNotified(true);
                plantationRepository.save(p);
            } catch (Exception e) {
                log.error("发送邮件失败: plantationId={}, error={}", p.getId(), e.getMessage());
            }
        }
    }

    private void sendWateringReminder(Plantation p) {
        User user = p.getUser();
        if (!user.isEmailNotify()) return;

        SimpleMailMessage msg = new SimpleMailMessage();
        msg.setFrom(mailFrom);
        msg.setTo(user.getEmail());

        String cropName = p.getCropType().getDisplayName();
        msg.setSubject("[王者农场] 浇水提醒 - " + cropName);

        DateTimeFormatter fmt = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm");
        StringBuilder text = new StringBuilder();
        text.append("您好！您的王者农场作物需要浇水了！\n\n");
        text.append("作物：").append(cropName).append("\n");
        text.append("已浇水：").append(p.getWateredCount()).append("/4 次\n");
        text.append("下次浇水时间：").append(p.getNextWateringTime().format(fmt)).append("\n");
        text.append("播种时间：").append(p.getSowingTime().format(fmt)).append("\n\n");

        if (user.getQq() != null && !user.getQq().isEmpty()) {
            text.append("QQ号：").append(user.getQq()).append("\n");
        }
        if (user.getWechat() != null && !user.getWechat().isEmpty()) {
            text.append("微信号：").append(user.getWechat()).append("\n");
        }

        text.append("\n请及时登录游戏浇水，避免错过加速窗口！");
        msg.setText(text.toString());

        mailSender.send(msg);
        log.info("已发送浇水提醒邮件到: {}", user.getEmail());
    }
}
