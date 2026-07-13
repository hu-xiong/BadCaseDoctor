package com.farm.calculator.service;

import com.farm.calculator.model.CropType;
import org.springframework.stereotype.Service;

import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;

/**
 * 浇水计算服务
 * 基于王者荣耀农场实际规则：
 * - 浇水后最短成熟时间 = 原周期 x 11/15
 * - 浇水节点：播种后 0, T/3, 2T/3, 11T/15
 */
@Service
public class WaterCalculatorService {

    /**
     * 计算某作物的4次浇水时间节点
     * @param cropType 作物类型
     * @param sowingTime 播种时间
     * @return 4次浇水的时间点列表（第1次即为播种时）
     */
    public List<LocalDateTime> getWateringSchedule(CropType cropType, LocalDateTime sowingTime) {
        int[] nodes = cropType.getWateringNodes();
        List<LocalDateTime> schedule = new ArrayList<>();
        for (int minutes : nodes) {
            schedule.add(sowingTime.plusMinutes(minutes));
        }
        return schedule;
    }

    /**
     * 计算下次浇水时间
     * @param cropType 作物类型
     * @param sowingTime 播种时间
     * @param wateredCount 已浇水次数
     * @return 下次浇水时间（若已浇满4次则返回null）
     */
    public LocalDateTime getNextWateringTime(CropType cropType, LocalDateTime sowingTime, int wateredCount) {
        if (wateredCount >= 4) return null;
        int[] nodes = cropType.getWateringNodes();
        return sowingTime.plusMinutes(nodes[wateredCount]);
    }

    /**
     * 判断是否已错过浇水（超过节点30分钟未浇）
     */
    public boolean isOverdue(CropType cropType, LocalDateTime sowingTime, int wateredCount, LocalDateTime now) {
        if (wateredCount >= 4) return false;
        LocalDateTime nextTime = getNextWateringTime(cropType, sowingTime, wateredCount);
        return now.isAfter(nextTime.plusMinutes(30));
    }

    /**
     * 浇水后最短成熟时间（从播种到成熟）
     */
    public LocalDateTime getMinHarvestTime(CropType cropType, LocalDateTime sowingTime) {
        return sowingTime.plusMinutes(cropType.getMinWateredMinutes());
    }
}
