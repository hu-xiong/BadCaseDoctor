package com.farm.calculator.model;

import jakarta.persistence.*;
import java.time.LocalDateTime;

/**
 * 用户实体
 */
@Entity
@Table(name = "users")
public class User {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true)
    private String email;

    @Column(nullable = false)
    private String password;

    /** QQ号 */
    private String qq;

    /** 微信号 */
    private String wechat;

    /** 是否启用邮件通知 */
    @Column(nullable = false)
    private boolean emailNotify = true;

    @Column(nullable = false, updatable = false)
    private LocalDateTime createdAt;

    @PrePersist
    protected void onCreate() {
        this.createdAt = LocalDateTime.now();
    }

    // --- getters / setters ---
    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public String getEmail() { return email; }
    public void setEmail(String email) { this.email = email; }
    public String getPassword() { return password; }
    public void setPassword(String password) { this.password = password; }
    public String getQq() { return qq; }
    public void setQq(String qq) { this.qq = qq; }
    public String getWechat() { return wechat; }
    public void setWechat(String wechat) { this.wechat = wechat; }
    public boolean isEmailNotify() { return emailNotify; }
    public void setEmailNotify(boolean emailNotify) { this.emailNotify = emailNotify; }
    public LocalDateTime getCreatedAt() { return createdAt; }
    public void setCreatedAt(LocalDateTime createdAt) { this.createdAt = createdAt; }
}
