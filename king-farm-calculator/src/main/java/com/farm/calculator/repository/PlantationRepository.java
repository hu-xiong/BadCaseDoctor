package com.farm.calculator.repository;

import com.farm.calculator.model.Plantation;
import com.farm.calculator.model.User;
import org.springframework.data.jpa.repository.JpaRepository;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Optional;

public interface PlantationRepository extends JpaRepository<Plantation, Long> {
    List<Plantation> findByUserOrderBySowingTimeDesc(User user);
    Optional<Plantation> findByIdAndUser(Long id, User user);

    /** 查找需要提醒的：生长中、未通知、下次浇水时间在指定范围内 */
    List<Plantation> findByStatusAndNotifiedAndNextWateringTimeBetween(
            Plantation.Status status, boolean notified,
            LocalDateTime start, LocalDateTime end);

    /** 查找已过浇水节点的 */
    List<Plantation> findByStatusAndNextWateringTimeBefore(
            Plantation.Status status, LocalDateTime time);
}
