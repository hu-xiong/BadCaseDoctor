package com.farm.calculator.model;

import jakarta.persistence.*;
import java.time.LocalDateTime;

/**
 * 浇水记录
 */
@Entity
@Table(name = "watering_records")
public class WateringRecord {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    /** 关联种植记录 */
    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "plantation_id", nullable = false)
    private Plantation plantation;

    /** 浇水时间 */
    @Column(nullable = false)
    private LocalDateTime wateredAt;

    /** 备注（第几次浇水） */
    private String notes;

    @Column(nullable = false, updatable = false)
    private LocalDateTime createdAt;

    @PrePersist
    protected void onCreate() {
        this.createdAt = LocalDateTime.now();
    }

    // --- getters / setters ---
    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public Plantation getPlantation() { return plantation; }
    public void setPlantation(Plantation plantation) { this.plantation = plantation; }
    public LocalDateTime getWateredAt() { return wateredAt; }
    public void setWateredAt(LocalDateTime wateredAt) { this.wateredAt = wateredAt; }
    public String getNotes() { return notes; }
    public void setNotes(String notes) { this.notes = notes; }
    public LocalDateTime getCreatedAt() { return createdAt; }
    public void setCreatedAt(LocalDateTime createdAt) { this.createdAt = createdAt; }
}
