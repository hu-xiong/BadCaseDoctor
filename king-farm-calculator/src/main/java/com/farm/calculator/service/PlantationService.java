package com.farm.calculator.service;

import com.farm.calculator.model.CropType;
import com.farm.calculator.model.Plantation;
import com.farm.calculator.model.User;
import com.farm.calculator.model.WateringRecord;
import com.farm.calculator.repository.PlantationRepository;
import com.farm.calculator.repository.WateringRecordRepository;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.List;

@Service
public class PlantationService {

    @Autowired
    private PlantationRepository plantationRepository;

    @Autowired
    private WateringRecordRepository wateringRecordRepository;

    @Autowired
    private WaterCalculatorService calculatorService;

    /**
     * 新建种植记录
     */
    @Transactional
    public Plantation createPlantation(User user, String cropTypeName, LocalDateTime sowingTime) {
        CropType cropType = CropType.valueOf(cropTypeName);

        Plantation p = new Plantation();
        p.setUser(user);
        p.setCropType(cropType);
        p.setSowingTime(sowingTime);
        p.setWateredCount(0);

        // 计算第1次浇水时间（即播种时）
        p.setNextWateringTime(sowingTime);

        return plantationRepository.save(p);
    }

    /**
     * 执行浇水
     */
    @Transactional
    public Plantation water(Long plantationId, User user) {
        Plantation p = plantationRepository.findByIdAndUser(plantationId, user)
                .orElseThrow(() -> new RuntimeException("种植记录不存在"));

        if (p.getStatus() != Plantation.Status.GROWING) {
            throw new RuntimeException("该作物已收获或已错过浇水");
        }
        if (p.getWateredCount() >= 4) {
            throw new RuntimeException("已浇满4次，无需再浇水");
        }

        CropType cropType = p.getCropType();
        int newCount = p.getWateredCount() + 1;

        // 记录浇水
        WateringRecord record = new WateringRecord();
        record.setPlantation(p);
        record.setWateredAt(LocalDateTime.now());
        record.setNotes("第" + newCount + "次浇水");
        wateringRecordRepository.save(record);

        // 更新种植记录
        p.setWateredCount(newCount);
        p.setNotified(false);

        if (newCount >= 4) {
            // 第4次浇水完成，可以收获了
            p.setNextWateringTime(null);
            p.setStatus(Plantation.Status.HARVESTED);
        } else {
            // 计算下次浇水时间
            LocalDateTime nextTime = calculatorService.getNextWateringTime(
                    cropType, p.getSowingTime(), newCount);
            p.setNextWateringTime(nextTime);
        }

        return plantationRepository.save(p);
    }

    /**
     * 获取用户的所有种植记录
     */
    public List<Plantation> getUserPlantations(User user) {
        return plantationRepository.findByUserOrderBySowingTimeDesc(user);
    }

    /**
     * 收获作物
     */
    @Transactional
    public Plantation harvest(Long plantationId, User user) {
        Plantation p = plantationRepository.findByIdAndUser(plantationId, user)
                .orElseThrow(() -> new RuntimeException("种植记录不存在"));
        p.setStatus(Plantation.Status.HARVESTED);
        p.setNextWateringTime(null);
        return plantationRepository.save(p);
    }

    /**
     * 检查并标记超时的种植记录
     */
    @Transactional
    public void checkOverdue() {
        List<Plantation> growing = plantationRepository
                .findByStatusAndNextWateringTimeBefore(
                        Plantation.Status.GROWING, LocalDateTime.now());

        for (Plantation p : growing) {
            // 如果已经超过下次浇水时间30分钟，标记为错过
            if (p.getNextWateringTime() != null
                    && p.getWateredCount() < 4
                    && LocalDateTime.now().isAfter(p.getNextWateringTime().plusMinutes(30))) {
                p.setStatus(Plantation.Status.MISSED);
                plantationRepository.save(p);
            }
        }
    }
}
