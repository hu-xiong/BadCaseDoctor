package com.farm.calculator.model;

import jakarta.persistence.*;
import java.time.LocalDateTime;

/**
 * 种植记录
 */
@Entity
@Table(name = "plantations")
public class Plantation {

    public enum Status {
        GROWING,    // 生长中
        HARVESTED,  // 已收获
        MISSED      // 错过浇水
    }

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    /** 所属用户 */
    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "user_id", nullable = false)
    private User user;

    /** 作物类型（存枚举名） */
    @Column(nullable = false)
    private String cropTypeName;

    /** 播种时间 */
    @Column(nullable = false)
    private LocalDateTime sowingTime;

    /** 下次浇水时间 */
    private LocalDateTime nextWateringTime;

    /** 已浇水次数（0-4） */
    @Column(nullable = false)
    private int wateredCount = 0;

    /** 状态 */
    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private Status status = Status.GROWING;

    /** 是否已发送过提醒 */
    private boolean notified = false;

    @Column(nullable = false, updatable = false)
    private LocalDateTime createdAt;

    @PrePersist
    protected void onCreate() {
        this.createdAt = LocalDateTime.now();
    }

    // --- 辅助方法 ---
    public CropType getCropType() {
        return CropType.valueOf(cropTypeName);
    }

    public void setCropType(CropType cropType) {
        this.cropTypeName = cropType.name();
    }

    /** 是否还需要浇水（次数 < 4 且状态为生长中） */
    public boolean needsWatering() {
        return wateredCount < 4 && status == Status.GROWING;
    }

    // --- getters / setters ---
    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public User getUser() { return user; }
    public void setUser(User user) { this.user = user; }
    public String getCropTypeName() { return cropTypeName; }
    public void setCropTypeName(String cropTypeName) { this.cropTypeName = cropTypeName; }
    public LocalDateTime getSowingTime() { return sowingTime; }
    public void setSowingTime(LocalDateTime sowingTime) { this.sowingTime = sowingTime; }
    public LocalDateTime getNextWateringTime() { return nextWateringTime; }
    public void setNextWateringTime(LocalDateTime nextWateringTime) { this.nextWateringTime = nextWateringTime; }
    public int getWateredCount() { return wateredCount; }
    public void setWateredCount(int wateredCount) { this.wateredCount = wateredCount; }
    public Status getStatus() { return status; }
    public void setStatus(Status status) { this.status = status; }
    public boolean isNotified() { return notified; }
    public void setNotified(boolean notified) { this.notified = notified; }
    public LocalDateTime getCreatedAt() { return createdAt; }
    public void setCreatedAt(LocalDateTime createdAt) { this.createdAt = createdAt; }
}
